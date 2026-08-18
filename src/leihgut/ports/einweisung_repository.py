"""Port für den Zugriff auf Einweisungen (UC-07/UC-08, SI-07/SI-08)."""
from typing import Protocol

from leihgut.domain.einweisung import Einweisung


class EinweisungRepository(Protocol):
    def find_by_id(self, einweisung_id: str) -> Einweisung | None:
        """Liefert die Einweisung oder ``None`` (SI-08)."""
        ...

    def find_gueltige(
        self, mitglied_id: str, kategorie_id: str
    ) -> Einweisung | None:
        """Liefert die gültige (nicht widerrufene) Einweisung für die
        Kombination aus Mitglied und Kategorie, falls vorhanden — Grundlage
        für BR-EIN-01 (Duplikatsprüfung, SI-07) und BR-AUS-04 (Ausgabe-
        Prüfung in EPIC-A)."""
        ...

    def insert(self, einweisung: Einweisung) -> None:
        """Legt eine neue Einweisung an (SI-07). Aufrufer hat bereits
        BR-EIN-01 (keine doppelte gültige Einweisung) geprüft."""
        ...

    def widerrufen(self, einweisung_id: str, widerrufen_am: str) -> None:
        """Markiert die Einweisung als widerrufen (BR-EIN-03, SI-08).
        Aufrufer hat bereits geprüft, dass die Einweisung existiert und
        noch gültig ist."""
        ...
