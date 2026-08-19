"""Domänenmodell für Vormerkungen (UC-05, BR-VOR-01..03).

`spec-domain-model.adoc`: eine Vormerkung ist eine FIFO-Reservierung auf
eine Kategorie. Jedes Mitglied kann pro Kategorie höchstens eine offene
Vormerkung haben (BR-VOR-01). Die Reihenfolge entscheidet, wer zuerst einen
zurückgegebenen Gegenstand bekommt (FIFO, BR-VOR-02).
"""
from dataclasses import dataclass
from enum import Enum


class VormerkungStatus(str, Enum):
    OFFEN = "offen"
    AUTOMATISCH_ABGESAGT = "automatisch_abgesagt"
    MANUELL_ABGESAGT = "manuell_abgesagt"


@dataclass(frozen=True)
class Vormerkung:
    vormerkung_id: str
    kategorie_id: str
    mitglied_id: str
    erstellt_am: str
    status: VormerkungStatus
    reihenfolge: int

    def ist_offen(self) -> bool:
        """BR-VOR-02: offen wenn status = OFFEN."""
        return self.status == VormerkungStatus.OFFEN
