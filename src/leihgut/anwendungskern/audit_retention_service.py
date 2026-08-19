"""Audit-Log Retention Service (UC-Maintenance).

Periodischer Cleanup veralteter Audit-Einträge gemäß Compliance-Policy:
- Hot (< 90 Tage): IN audit_log table (queryable)
- Warm (90 Tage - 1 Jahr): Archiviert (optional)
- Cold (> 1 Jahr): Gelöscht aus aktiver DB (deferred)

Immutability-Safe: ADR-009 Trigger verhindert DELETE auf audit_log.
Strategie: Schreibe Retention-Record (ereignisart='retention_cleanup').
Clients filtern dann: WHERE ereignisart != 'retention_cleanup' für operative Logs.

Nutzung:
  - Täglich über Scheduler (z.B. Celery, APScheduler)
  - Oder manuell via REST Endpoint /admin/audit-log/cleanup
"""
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from leihgut.ports.clock import Clock


@dataclass(frozen=True)
class RetentionPolicy:
    """Aufbewahrungsrichtlinie für Audit-Logs."""
    
    hot_days: int = 90  # Wie viele Tage im audit_log behalten
    warm_days: int = 365  # Wie viele Tage optional archivieren
    cold_days: int = 7 * 365  # Danach löschen (MVP: nicht implementiert)
    archive_enabled: bool = False  # Warm-Tier archivieren? (MVP: deactivated)


@dataclass(frozen=True)
class RetentionResult:
    """Ergebnis des Cleanup-Laufs."""
    
    deleted_count: int  # Gelöschte Einträge
    archived_count: int  # Archivierte Einträge (warm)
    oldest_kept_timestamp: str  # Ältester noch vorhandener Eintrag
    deleted_oldest_timestamp: Optional[str]  # Ältester gelöschter Eintrag


def cleanup_audit_log(
    conn: sqlite3.Connection,
    clock: Clock,
    policy: RetentionPolicy = RetentionPolicy(),
) -> RetentionResult:
    """Audit-Log Cleanup nach Retention-Policy durchführen.
    
    ADR-009: Trigger verhindert DELETE auf audit_log (Unveränderlichkeit).
    Strategie: Schreibe einen Retention-Record (ereignisart='retention_cleanup').
    Clients filtern: WHERE ereignisart != 'retention_cleanup' für operative Logs.
    
    Transactional: Entweder kompleter Cleanup oder nichts.
    """
    jetzt = clock.jetzt()
    
    # Berechne Cutoff-Datum: älter als hot_days Tage
    cutoff_date = (jetzt - timedelta(days=policy.hot_days)).strftime("%Y-%m-%dT%H:%M:%S")
    
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Schritt 1: Einträge die "gelöscht" werden würden analysieren
        oldest_deleted = conn.execute(
            "SELECT MIN(zeitstempel) FROM audit_log WHERE zeitstempel < ? AND ereignisart != 'retention_cleanup'",
            (cutoff_date,)
        ).fetchone()[0]
        
        deleted_count = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE zeitstempel < ? AND ereignisart != 'retention_cleanup'",
            (cutoff_date,)
        ).fetchone()[0]
        
        # Schritt 2: Optional archivieren (warm tier)
        archived_count = 0
        if policy.archive_enabled:
            # Kopiere alte Einträge in archive table (falls vorhanden)
            try:
                conn.execute(
                    "INSERT INTO audit_log_archive "
                    "SELECT * FROM audit_log WHERE zeitstempel < ? AND ereignisart != 'retention_cleanup'",
                    (cutoff_date,)
                )
                archived_count = conn.execute(
                    "SELECT changes()"
                ).fetchone()[0]
            except sqlite3.OperationalError:
                # audit_log_archive table existiert nicht → ignorieren
                archived_count = 0
        
        # Schritt 3: Schreibe Retention-Record
        # Dies ist der einzige Ort, an dem "Löschung" dokumentiert wird.
        # Dadurch bleibt audit_log immutable (nur INSERT, kein DELETE).
        conn.execute(
            "INSERT INTO audit_log "
            "(zeitstempel, aggregat, aggregat_id, ereignisart, rolle, werte_vorher, werte_nachher) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                jetzt.isoformat(),
                "AuditLog",
                "system",
                "retention_cleanup",
                "system",
                None,
                json.dumps({
                    "deleted_count": deleted_count,
                    "oldest_deleted": oldest_deleted,
                    "cutoff_date": cutoff_date,
                    "policy": {
                        "hot_days": policy.hot_days,
                        "warm_days": policy.warm_days,
                        "cold_days": policy.cold_days,
                        "archive_enabled": policy.archive_enabled,
                    }
                })
            )
        )
        
        conn.commit()
        
        # Berechne oldest_kept (ältester Eintrag der NICHT gelöscht wurde)
        oldest_kept = conn.execute(
            "SELECT MIN(zeitstempel) FROM audit_log WHERE zeitstempel >= ? AND ereignisart != 'retention_cleanup'",
            (cutoff_date,)
        ).fetchone()[0]
        
        return RetentionResult(
            deleted_count=deleted_count,
            archived_count=archived_count,
            oldest_kept_timestamp=oldest_kept or "N/A",
            deleted_oldest_timestamp=oldest_deleted,
        )
    
    except Exception:
        conn.rollback()
        raise


def get_audit_log_stats(conn: sqlite3.Connection) -> dict:
    """Statistiken über current audit_log Größe ermitteln.
    
    Filtert Retention-Cleanup-Einträge (ereignisart='retention_cleanup')
    aus der Berechnung, um nur operative Audit-Einträge zu zählen.
    
    Returns:
        {
            "total_entries": int,
            "oldest_entry": str,  # ISO timestamp
            "newest_entry": str,
            "daily_rate": float,  # Einträge pro Tag (approx)
            "estimated_size_mb": float,
        }
    """
    stats = conn.execute(
        """
        SELECT 
            COUNT(*) as total_entries,
            MIN(zeitstempel) as oldest,
            MAX(zeitstempel) as newest
        FROM audit_log
        WHERE ereignisart != 'retention_cleanup'
        """
    ).fetchone()
    
    total, oldest, newest = stats
    
    if total == 0:
        return {
            "total_entries": 0,
            "oldest_entry": None,
            "newest_entry": None,
            "daily_rate": 0.0,
            "estimated_size_mb": 0.0,
        }
    
    # Berechne daily rate
    if oldest and newest:
        oldest_dt = datetime.fromisoformat(oldest)
        newest_dt = datetime.fromisoformat(newest)
        days_span = max(1, (newest_dt - oldest_dt).days)
        daily_rate = total / days_span
    else:
        daily_rate = 0.0
    
    # Geschätzte Größe (200 bytes pro Eintrag als Durchschnitt)
    estimated_size_bytes = total * 200
    estimated_size_mb = estimated_size_bytes / (1024 * 1024)
    
    return {
        "total_entries": total,
        "oldest_entry": oldest,
        "newest_entry": newest,
        "daily_rate": round(daily_rate, 1),
        "estimated_size_mb": round(estimated_size_mb, 2),
    }
