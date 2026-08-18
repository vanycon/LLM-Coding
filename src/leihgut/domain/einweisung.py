"""Domänenmodell für Einweisungen (UC-07/UC-08, BR-EIN-01..03).

`spec-domain-model.adoc`: eine Einweisung ist unbefristet gültig, bis sie
explizit widerrufen wird (BR-EIN-02) — kein Ablaufdatum, nur ein optionaler
`widerrufen_am`-Zeitstempel.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Einweisung:
    einweisung_id: str
    mitglied_id: str
    kategorie_id: str
    erstellt_am: str
    widerrufen_am: str | None = None

    def ist_gueltig(self) -> bool:
        """BR-EIN-02: gültig, solange kein Widerruf erfolgt ist."""
        return self.widerrufen_am is None
