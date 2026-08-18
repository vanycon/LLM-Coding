"""Domänenmodell: Gegenstand.

Siehe src/docs/specs/spec-domain-model.adoc, Entity-Modell und
Validierungsregeln (BR-KAT-01..04).
"""
from dataclasses import dataclass
from enum import Enum


class GegenstandZustand(str, Enum):
    """Zustände laut Entity-Modell (spec-domain-model.adoc, State Machine
    Gegenstand)."""

    VERFUEGBAR = "verfuegbar"
    AUSGELIEHEN = "ausgeliehen"
    IN_PRUEFUNG = "in_pruefung"
    WARTUNGSFAELLIG = "wartungsfaellig"
    RESERVIERT = "reserviert"
    AUSGEMUSTERT = "ausgemustert"


@dataclass(frozen=True)
class Gegenstand:
    """Gegenstand-Aggregat (spec-domain-model.adoc, Entity-Modell)."""

    inventarnummer: str
    kategorie_id: str
    zustand: GegenstandZustand
    wiederbeschaffungswert_cent: int
    nutzungszaehler: int = 0
