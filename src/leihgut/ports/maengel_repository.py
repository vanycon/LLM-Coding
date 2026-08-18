"""Port für den Zugriff auf die Mängelliste eines Gegenstands (BR-RUP-05,
UC-04)."""
from typing import Protocol

from leihgut.domain.maengel import MaengelEintrag


class MaengelRepository(Protocol):
    def find_by_gegenstand(self, gegenstand_id: str) -> list[MaengelEintrag]:
        """Liefert alle bisher für diesen Gegenstand festgestellten Mängel
        (über alle Prüfprotokolle hinweg) — Grundlage für den
        Neuheitsabgleich nach BR-RUP-05."""
        ...
