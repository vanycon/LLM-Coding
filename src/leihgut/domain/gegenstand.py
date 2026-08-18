"""Domänenmodell: Gegenstand (UC-10 Verfügbarkeit prüfen, Ausschnitt).

Nur der für den Walking Skeleton (Skeleton-01, siehe
``src/docs/implementation/backlog.adoc``) benötigte Ausschnitt. Wird in
EPIC-D (Katalog pflegen) um Anlage- und Änderungsregeln (BR-KAT-01..04,
siehe ``src/docs/specs/spec-domain-model.adoc``) erweitert.
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
    """Ausschnitt des Gegenstand-Aggregats für UC-10 (nur Lesezugriff)."""

    inventarnummer: str
    kategorie_id: str
    zustand: GegenstandZustand
