"""Port für den Zugriff auf Kategorien (BR-KAT-02, UC-09)."""
from typing import Protocol

from leihgut.domain.kategorie import Kategorie


class KategorieRepository(Protocol):
    def find_by_id(self, kategorie_id: str) -> Kategorie | None:
        ...

    def insert(self, kategorie: Kategorie) -> None:
        ...

    def update(self, kategorie: Kategorie) -> None:
        ...
