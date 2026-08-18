"""Port für den Zugriff auf Gegenstände.

Ein Port pro Aggregat, keine generische "Datenbank"-Schnittstelle — verhindert
Lecks von SQL-Details in den Anwendungskern
(``src/docs/arc42/chapters/05_building_block_view.adoc``, "Wichtige
Schnittstellen").
"""
from typing import Protocol

from leihgut.domain.gegenstand import Gegenstand


class GegenstandRepository(Protocol):
    def find_by_inventarnummer(self, inventarnummer: str) -> Gegenstand | None:
        """Liefert den Gegenstand oder ``None``, wenn die Inventarnummer
        nicht existiert (SI-10)."""
        ...
