"""Anwendungsdienst für UC-07 (Einweisung erfassen) und UC-08 (Einweisung
widerrufen) / SI-07, SI-08.

IOSP: `einweisung_id` wird hier (Integration) erzeugt, nicht in der
Operation; die Prüf-Operationen selbst greifen auf keine Ports zu und sind
damit isoliert testbar (08_concepts.adoc, Abschnitt Test, Ebene "Unit").
"""
import uuid
from dataclasses import dataclass

from leihgut.domain.einweisung import Einweisung
from leihgut.ports.clock import Clock
from leihgut.ports.einweisung_repository import EinweisungRepository


@dataclass(frozen=True)
class EinweisungBestehtBereits:
    """SI-07-Ablehnung: `409 EINWEISUNG_BESTEHT_BEREITS` (BR-EIN-01)."""

    mitglied_id: str
    kategorie_id: str


@dataclass(frozen=True)
class EinweisungNichtGefunden:
    """SI-08-Ablehnung: `404 EINWEISUNG_NICHT_GEFUNDEN`."""

    einweisung_id: str


@dataclass(frozen=True)
class BereitsWiderrufen:
    """SI-08-Ablehnung: `409 BEREITS_WIDERRUFEN`."""

    einweisung_id: str


EinweisungAblehnung = (
    EinweisungBestehtBereits | EinweisungNichtGefunden | BereitsWiderrufen
)


def einweisung_erfassen(
    repo: EinweisungRepository,
    clock: Clock,
    mitglied_id: str,
    kategorie_id: str,
) -> Einweisung | EinweisungAblehnung:
    """UC-07: legt eine unbefristete Einweisung an (BR-EIN-01, BR-EIN-02)."""
    if repo.find_gueltige(mitglied_id, kategorie_id) is not None:
        return EinweisungBestehtBereits(mitglied_id, kategorie_id)
    einweisung = Einweisung(
        einweisung_id=str(uuid.uuid4()),
        mitglied_id=mitglied_id,
        kategorie_id=kategorie_id,
        erstellt_am=clock.jetzt(),
        widerrufen_am=None,
    )
    repo.insert(einweisung)
    return einweisung


def einweisung_widerrufen(
    repo: EinweisungRepository,
    clock: Clock,
    einweisung_id: str,
) -> Einweisung | EinweisungAblehnung:
    """UC-08: markiert eine gültige Einweisung als widerrufen (BR-EIN-03)."""
    bestehende = repo.find_by_id(einweisung_id)
    if bestehende is None:
        return EinweisungNichtGefunden(einweisung_id)
    if not bestehende.ist_gueltig():
        return BereitsWiderrufen(einweisung_id)
    widerrufen_am = clock.jetzt()
    repo.widerrufen(einweisung_id, widerrufen_am)
    return Einweisung(
        einweisung_id=bestehende.einweisung_id,
        mitglied_id=bestehende.mitglied_id,
        kategorie_id=bestehende.kategorie_id,
        erstellt_am=bestehende.erstellt_am,
        widerrufen_am=widerrufen_am,
    )
