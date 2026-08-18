"""Port für den atomaren Prüfabschluss (UC-04, SI-04).

Anders als bei den bisherigen Aggregat-Repositories (je ein `commit()` pro
Aufruf) verlangt diese Story ausdrücklich, dass Kautionsbuchung,
Zustandswechsel und Audit-Eintrag *in einer* Transaktion laufen (Backlog,
`epic-b-pruefung-kaution.adoc`). Analog zu ADR-007
(`SqliteAusleiheRepository.insert()`: `BEGIN IMMEDIATE` direkt im Adapter,
keine generische Unit-of-Work-Abstraktion) bündelt dieser Port alle
Schreibvorgänge dieses einen Anwendungsfalls in einer einzigen Methode.
"""
from typing import Protocol

from leihgut.domain.audit_log import AuditLogEintrag
from leihgut.domain.ausleihe import Ausleihe
from leihgut.domain.gegenstand import Gegenstand
from leihgut.domain.kautionsbewegung import Kautionsbewegung
from leihgut.domain.maengel import MaengelEintrag
from leihgut.domain.pruefprotokoll import Pruefprotokoll


class PruefabschlussRepository(Protocol):
    def abschliessen(
        self,
        ausleihe: Ausleihe,
        gegenstand: Gegenstand,
        pruefprotokoll: Pruefprotokoll,
        neue_maengel: list[MaengelEintrag],
        kautionsbewegungen: list[Kautionsbewegung],
        audit_eintrag: AuditLogEintrag,
    ) -> None:
        """Persistiert Ausleihe-Update, Gegenstand-Update,
        Prüfprotokoll-/Mängel-Inserts, Kautionsbewegungs-Inserts und den
        Audit-Log-Eintrag atomar in einer einzigen SQLite-Transaktion
        (`BEGIN IMMEDIATE` … `COMMIT`)."""
        ...
