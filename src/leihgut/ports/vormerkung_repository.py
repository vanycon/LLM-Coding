"""Port: Vormerkung Repository."""
from abc import ABC, abstractmethod

from leihgut.domain.vormerkung import Vormerkung


class VormerkungRepository(ABC):
    """Persistence Port für Vormerkung Aggregate."""

    @abstractmethod
    def find_by_id(self, vormerkung_id: str) -> Vormerkung | None:
        """Finde Vormerkung nach ID (egal ob offen oder abgesagt)."""
        pass

    @abstractmethod
    def find_offene_je_mitglied_kategorie(self, mitglied_id: str, kategorie_id: str) -> Vormerkung | None:
        """Finde offene Vormerkung für (Mitglied, Kategorie) oder None."""
        pass

    @abstractmethod
    def find_offene_je_kategorie_sortiert_nach_reihenfolge(self, kategorie_id: str) -> list[Vormerkung]:
        """Finde alle offenen Vormerkungen für Kategorie, sortiert nach reihenfolge aufsteigend."""
        pass

    @abstractmethod
    def insert(self, vormerkung: Vormerkung) -> None:
        """Füge neue Vormerkung ein."""
        pass

    @abstractmethod
    def update(self, vormerkung: Vormerkung) -> None:
        """Update bestehende Vormerkung (z.B. Status ändern)."""
        pass
