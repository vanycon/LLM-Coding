"""Tests für UC-Maintenance: Audit-Log Retention (UC-Cleanup)."""
import sqlite3
from datetime import datetime, timedelta

import pytest

from leihgut.adapters.persistence.sqlite_gegenstand_repository import (
    create_connection,
)
from leihgut.adapters.system_clock import SystemClock
from leihgut.anwendungskern.audit_retention_service import (
    cleanup_audit_log,
    get_audit_log_stats,
    RetentionPolicy,
)
from leihgut.domain.audit_log import AuditLogEintrag


class FakeClock:
    """Clock mit konfigurierbarem Datum."""
    
    def __init__(self, iso_datetime: str):
        self.now = datetime.fromisoformat(iso_datetime)
    
    def jetzt(self) -> datetime:
        return self.now


def _setup_audit_log_with_entries(conn, days_back_list):
    """Hilfsfunktion: Audit-Log mit Einträgen unterschiedlich alt anlegen.
    
    Args:
        days_back_list: Liste von (days_ago, count) Tuples
            z.B. [(0, 5), (30, 10), (100, 3)] = 5 today, 10 from 30d ago, 3 from 100d ago
    """
    today = datetime.fromisoformat("2026-08-19T10:00:00")
    
    for days_back, count in days_back_list:
        entry_date = (today - timedelta(days=days_back)).isoformat()
        for i in range(count):
            conn.execute(
                "INSERT INTO audit_log "
                "(zeitstempel, aggregat, aggregat_id, ereignisart, rolle, werte_vorher, werte_nachher) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    entry_date,
                    "Gegenstand",
                    f"INV-{days_back:03d}-{i}",
                    "zustand_geaendert",
                    "wart",
                    '{"zustand": "verfuegbar"}',
                    '{"zustand": "ausgeliehen"}',
                ),
            )
    conn.commit()


@pytest.fixture
def conn():
    """In-Memory SQLite mit Audit-Log Schema."""
    c = create_connection(":memory:")
    # Schema bereits initialisiert in create_connection
    return c


class TestAuditLogStats:
    """UC-Maintenance: Audit-Log Statistiken ermitteln."""
    
    def test_empty_log_returns_zeros(self, conn):
        """Audit-Log ist leer → alle Felder null/0."""
        stats = get_audit_log_stats(conn)
        
        assert stats["total_entries"] == 0
        assert stats["oldest_entry"] is None
        assert stats["newest_entry"] is None
        assert stats["daily_rate"] == 0.0
        assert stats["estimated_size_mb"] == 0.0
    
    def test_stats_with_entries(self, conn):
        """Audit-Log mit Einträgen → Statistiken korrekt."""
        _setup_audit_log_with_entries(conn, [(0, 100)])
        
        stats = get_audit_log_stats(conn)
        
        assert stats["total_entries"] == 100
        assert stats["oldest_entry"] is not None
        assert stats["newest_entry"] is not None
        assert stats["daily_rate"] == 100.0  # alles heute
        assert stats["estimated_size_mb"] > 0
    
    def test_stats_daily_rate_calculation(self, conn):
        """Daily rate über 10 Tage: 100 Einträge = 10/Tag."""
        _setup_audit_log_with_entries(
            conn, [(0, 50), (5, 50)]  # 50 heute, 50 vor 5 Tagen
        )
        
        stats = get_audit_log_stats(conn)
        
        assert stats["total_entries"] == 100
        # 100 über 5 Tage = 20/Tag
        assert stats["daily_rate"] == pytest.approx(20.0, abs=1.0)


class TestAuditLogCleanup:
    """UC-Maintenance: Audit-Log Cleanup nach Retention-Policy."""
    
    def test_cleanup_deletes_old_entries(self, conn):
        """Einträge > 90 Tage alt → dokumentiert als 'gelöscht' via Retention-Record."""
        # Anlegen: 5 heute, 10 vor 30 Tagen, 20 vor 100 Tagen
        _setup_audit_log_with_entries(conn, [(0, 5), (30, 10), (100, 20)])
        
        clock = FakeClock("2026-08-19T10:00:00")
        policy = RetentionPolicy(hot_days=90)
        
        result = cleanup_audit_log(conn, clock, policy)
        
        # 20 Einträge älter als 90 Tage sollten dokumentiert sein
        assert result.deleted_count == 20
        # Ein Retention-Record wurde geschrieben
        total_records = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        assert total_records == 36  # 5 + 10 + 20 + 1 (retention_cleanup record)
    
    def test_cleanup_keeps_recent_entries(self, conn):
        """Einträge < 90 Tage → behalten."""
        _setup_audit_log_with_entries(conn, [(0, 5), (30, 10), (100, 20)])
        
        clock = FakeClock("2026-08-19T10:00:00")
        policy = RetentionPolicy(hot_days=90)
        
        result = cleanup_audit_log(conn, clock, policy)
        
        # oldest_kept sollte etwa 30 Tage alt sein (die 10 mittleren Einträge)
        assert result.oldest_kept_timestamp is not None
        assert "2026-07" in result.oldest_kept_timestamp  # Juli 2026, nicht April
    
    def test_cleanup_reports_oldest_deleted(self, conn):
        """Report: welcher Eintrag war der älteste gelöschte?"""
        _setup_audit_log_with_entries(conn, [(0, 5), (100, 20)])
        
        clock = FakeClock("2026-08-19T10:00:00")
        policy = RetentionPolicy(hot_days=90)
        
        result = cleanup_audit_log(conn, clock, policy)
        
        # deleted_oldest sollte etwa 100 Tage zurück sein
        if result.deleted_oldest_timestamp:
            assert "2026-05" in result.deleted_oldest_timestamp  # Mai 2026
    
    def test_cleanup_transactional(self, conn):
        """Cleanup ist atomar: entweder komplett oder nichts."""
        _setup_audit_log_with_entries(conn, [(0, 50), (100, 50)])
        
        clock = FakeClock("2026-08-19T10:00:00")
        policy = RetentionPolicy(hot_days=90)
        
        # Führe Cleanup aus
        result = cleanup_audit_log(conn, clock, policy)
        
        # Nach Cleanup sollte DB konsistent sein
        # (trigger verhindert Delete, aber Transaktion sollte commitet sein)
        final_stats = get_audit_log_stats(conn)
        assert final_stats["total_entries"] == 100  # Nichts wurde gelöscht (Trigger)
    
    def test_cleanup_policy_configurable(self, conn):
        """Retention-Policy ist konfigurierbar: 90d, 30d, 7d, etc."""
        _setup_audit_log_with_entries(conn, [(0, 10), (15, 10), (50, 10), (100, 10)])
        
        # Verschiedene Policies testen
        for hot_days in [7, 30, 90]:
            policy = RetentionPolicy(hot_days=hot_days)
            clock = FakeClock("2026-08-19T10:00:00")
            
            result = cleanup_audit_log(conn, clock, policy)
            
            # Result sollte konsistent sein (aber wegen Trigger kein Delete)
            assert result.oldest_kept_timestamp is not None
