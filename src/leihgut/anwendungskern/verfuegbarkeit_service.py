"""Anwendungsdienst für UC-10 (Verfügbarkeit prüfen) — Skeleton-01.

IOSP: reine Integration (Komposition). Die einzige "Regel" hier ist
"existiert die Inventarnummer?" — sie gehört ins Repository/den Aufruf
selbst, nicht in eine eigene Operation, weil UC-10 keine weitere Fachlogik
hat (rein lesend, siehe ``spec-use-cases.adoc``, UC-10).
"""
from dataclasses import dataclass

from leihgut.domain.gegenstand import Gegenstand
from leihgut.ports.gegenstand_repository import GegenstandRepository


@dataclass(frozen=True)
class GegenstandNichtGefunden:
    """Ablehnung laut SI-10: ``404 NICHT_GEFUNDEN``."""

    inventarnummer: str


def verfuegbarkeit_pruefen(
    repo: GegenstandRepository, inventarnummer: str
) -> Gegenstand | GegenstandNichtGefunden:
    """UC-10: liefert den aktuellen Zustand eines Gegenstands oder eine
    Ablehnung, wenn die Inventarnummer nicht existiert."""
    gefunden = repo.find_by_inventarnummer(inventarnummer)
    if gefunden is None:
        return GegenstandNichtGefunden(inventarnummer)
    return gefunden
