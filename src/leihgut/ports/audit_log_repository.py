"""Port: Audit-Log persistieren (ADR-009, Append-Only).

Jeder Audit-Eintrag dokumentiert einen Zustandswechsel oder eine kritische
Geschäftsoperation. Die Implementierung schreibt immer in derselben Transaktion
wie die auslösende Fachänderung (04_solution_strategy.adoc, Nachvollziehbarkeit).
"""
from typing import Protocol

from leihgut.domain.audit_log import AuditLogEintrag


class AuditLogRepository(Protocol):
    """Port für Audit-Log-Persistierung."""

    def insert(self, eintrag: AuditLogEintrag) -> None:
        """Schreibt einen Audit-Eintrag.

        Wirft keine Exception — Fehler führt zur Transaktion-Rollback.
        Wird immer in derselben Transaktion wie die Fachdaten-Änderung
        aufgerufen.

        Args:
            eintrag: Der zu persistierende Audit-Eintrag.
        """
        ...
