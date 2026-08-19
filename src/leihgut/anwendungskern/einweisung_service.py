"""Anwendungsdienst für UC-07/UC-08 (Einweisung erfassen/widerrufen) / SI-07/SI-08.

IOSP: Reine Validierung ist von der Integration (Repository-Aufrufe) getrennt.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime

from leihgut.domain.einweisung import Einweisung
from leihgut.ports.einweisung_repository import EinweisungRepository
from leihgut.ports.kategorie_repository import KategorieRepository
from leihgut.ports.clock import Clock


@dataclass(frozen=True)
class KategorieNichtGefunden:
    """SI-07-Ablehnung: `404 KATEGORIE_NICHT_GEFUNDEN`."""

    kategorie_id: str


@dataclass(frozen=True)
class DuplikatEinweisung:
    """SI-07-Ablehnung: `409 DUPLIKAT` (BR-EIN-01, REQ-UC07-02)."""

    mitglied_id: str
    kategorie_id: str


@dataclass(frozen=True)
class EinweisungNichtGefunden:
    """SI-08-Ablehnung: `404 EINWEISUNG_NICHT_GEFUNDEN`."""

    einweisung_id: str


@dataclass(frozen=True)
class BereitsWiderrufen:
    """SI-08-Ablehnung: `409 BEREITS_WIDERRUFEN` (UC-08, bereits widerrufen_am IS NOT NULL)."""

    einweisung_id: str


EinweisungAblehnung = (
    KategorieNichtGefunden | DuplikatEinweisung | EinweisungNichtGefunden | BereitsWiderrufen
)


# --- Integration: Einweisung erfassen (UC-07 / SI-07) ---


def einweisung_erfassen(
    einweisung_repo: EinweisungRepository,
    kategorie_repo: KategorieRepository,
    clock: Clock,
    mitglied_id: str,
    kategorie_id: str,
) -> Einweisung | EinweisungAblehnung:
    """Einweisung erfassen (UC-07 / SI-07).

    Validierungsreihenfolge:
    1. Kategorie existiert (404)
    2. Keine gültige Einweisung für (Mitglied, Kategorie) existiert (409, BR-EIN-01)
    """
    # Prüfe: Kategorie existiert
    if kategorie_repo.find_by_id(kategorie_id) is None:
        return KategorieNichtGefunden(kategorie_id)

    # Prüfe: Keine gültige Einweisung vorhanden (BR-EIN-01)
    bestehende = einweisung_repo.find_gueltige_je_mitglied_kategorie(
        mitglied_id, kategorie_id
    )
    if bestehende is not None:
        return DuplikatEinweisung(mitglied_id, kategorie_id)

    # Anlegen: neue Einweisung mit erstellt_am = jetzt, widerrufen_am = NULL
    jetzt = clock.jetzt()
    neue_einweisung = Einweisung(
        einweisung_id=str(uuid.uuid4()),
        mitglied_id=mitglied_id,
        kategorie_id=kategorie_id,
        erstellt_am=jetzt,
        widerrufen_am=None,
    )
    einweisung_repo.insert(neue_einweisung)

    # Nach Insert: nochmal lesen, um die generierte ID zu bekommen
    gerade_angelegt = einweisung_repo.find_gueltige_je_mitglied_kategorie(
        mitglied_id, kategorie_id
    )
    assert gerade_angelegt is not None
    return gerade_angelegt


# --- Integration: Einweisung widerrufen (UC-08 / SI-08) ---


def einweisung_widerrufen(
    einweisung_repo: EinweisungRepository,
    clock: Clock,
    einweisung_id: str,
) -> Einweisung | EinweisungAblehnung:
    """Einweisung widerrufen (UC-08 / SI-08).

    Validierungsreihenfolge:
    1. Einweisung existiert & gültig (404)
    2. Noch nicht widerrufen (409)
    """
    einweisung = einweisung_repo.find_by_id(einweisung_id)
    if einweisung is None or einweisung.widerrufen_am is not None:
        # Wichtig: nicht unterscheiden zwischen "nicht vorhanden" und "bereits widerrufen"
        # bei der Abfrage. Aber die Ablehnung unterscheidet (404 vs. 409).
        if einweisung is None:
            return EinweisungNichtGefunden(einweisung_id)
        else:
            return BereitsWiderrufen(einweisung_id)

    # Widerrufen: widerrufen_am = jetzt
    jetzt = clock.jetzt()
    widerrufene = Einweisung(
        einweisung_id=einweisung.einweisung_id,
        mitglied_id=einweisung.mitglied_id,
        kategorie_id=einweisung.kategorie_id,
        erstellt_am=einweisung.erstellt_am,
        widerrufen_am=jetzt,
    )
    einweisung_repo.widerrufen(einweisung.einweisung_id, jetzt)
    return widerrufene
