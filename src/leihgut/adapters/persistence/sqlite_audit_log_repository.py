"""Adapter: Audit-Log in SQLite (Append-Only, unveränderlich durch Trigger).

Implementiert den AuditLogRepository-Port. Jeder insert() läuft in der bereits
offenen Transaktion des Anwendungsdienstes (kein eigener commit).
"""
import sqlite3

from leihgut.domain.audit_log import AuditLogEintrag


class SqliteAuditLogRepository:
    """SQLite-Adapter für Audit-Log."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(self, eintrag: AuditLogEintrag) -> None:
        """Schreibt einen Eintrag ins audit_log.

        Läuft in der bereits offenen Transaktion (kein commit hier).
        Die DB-Trigger (ADR-009) verhindern nachträgliche UPDATE/DELETE.
        """
        self.conn.execute(
            """INSERT INTO audit_log
               (zeitstempel, aggregat, aggregat_id, ereignisart, rolle, 
                werte_vorher, werte_nachher)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                eintrag.zeitstempel,
                eintrag.aggregat,
                eintrag.aggregat_id,
                eintrag.ereignisart,
                eintrag.rolle,
                eintrag.werte_vorher,
                eintrag.werte_nachher,
            ),
        )
