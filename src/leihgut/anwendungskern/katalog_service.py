"""Anwendungsdienst für UC-09 (Katalog pflegen) / SI-09.

IOSP: Operationen (Validierung) sind von der Integration (Repository-
Aufrufe) getrennt, damit die Validierungsregeln isoliert ohne Ports
getestet werden können (08_concepts.adoc, Abschnitt Test, Ebene "Unit").
"""
from dataclasses import dataclass

from leihgut.domain.gegenstand import Gegenstand, GegenstandZustand
from leihgut.domain.kategorie import Kategorie
from leihgut.ports.gegenstand_repository import GegenstandRepository
from leihgut.ports.kategorie_repository import KategorieRepository


@dataclass(frozen=True)
class InventarnummerVergeben:
    """SI-09-Ablehnung: `409 INVENTARNUMMER_VERGEBEN` (BR-KAT-01)."""

    inventarnummer: str


@dataclass(frozen=True)
class GegenstandNichtGefunden:
    """Ablehnung bei Änderung eines nicht existierenden Gegenstands.

    SI-09 spezifiziert diesen Fehlerfall für `PUT /gegenstaende/{...}` nicht
    explizit, aber der Fehlercode `GEGENSTAND_NICHT_GEFUNDEN` (404) ist in
    der Fehlercode-Übersicht bereits definiert (spec-system-interfaces.adoc)
    und wird hier konsistent wiederverwendet."""

    inventarnummer: str


@dataclass(frozen=True)
class KategorieNichtGefunden:
    """SI-09-Ablehnung: `404 KATEGORIE_NICHT_GEFUNDEN`."""

    kategorie_id: str


@dataclass(frozen=True)
class WertUngueltig:
    """SI-09-Ablehnung: `422 WERT_UNGUELTIG` (BR-KAT-02, BR-KAT-03)."""

    feld: str
    wert: int


KatalogAblehnung = (
    InventarnummerVergeben
    | GegenstandNichtGefunden
    | KategorieNichtGefunden
    | WertUngueltig
)


# --- Operation: reine Validierung, kein Port-Zugriff --------------------

def _kategorie_werte_pruefen(
    leihdauer_tage: int, wartungsintervall: int
) -> WertUngueltig | None:
    """BR-KAT-02: Leihdauer und Wartungsintervall müssen ganzzahlig > 0
    sein (per Typsystem bereits ganzzahlig, hier nur der Wertebereich)."""
    if leihdauer_tage <= 0:
        return WertUngueltig("leihdauerTage", leihdauer_tage)
    if wartungsintervall <= 0:
        return WertUngueltig("wartungsintervall", wartungsintervall)
    return None


def _wiederbeschaffungswert_pruefen(wert_cent: int) -> WertUngueltig | None:
    """BR-KAT-03: Wiederbeschaffungswert muss ganzzahlig > 0 sein."""
    if wert_cent <= 0:
        return WertUngueltig("wiederbeschaffungswertCent", wert_cent)
    return None


# --- Integration: Kategorie ----------------------------------------------

def kategorie_anlegen(
    repo: KategorieRepository,
    kategorie_id: str,
    name: str,
    leihdauer_tage: int,
    wartungsintervall: int,
    einweisungspflichtig: bool,
) -> Kategorie | KatalogAblehnung:
    fehler = _kategorie_werte_pruefen(leihdauer_tage, wartungsintervall)
    if fehler is not None:
        return fehler
    kategorie = Kategorie(
        kategorie_id=kategorie_id,
        name=name,
        leihdauer_tage=leihdauer_tage,
        wartungsintervall=wartungsintervall,
        einweisungspflichtig=einweisungspflichtig,
    )
    repo.insert(kategorie)
    return kategorie


def kategorie_aendern(
    repo: KategorieRepository,
    kategorie_id: str,
    leihdauer_tage: int,
    wartungsintervall: int,
    einweisungspflichtig: bool,
) -> Kategorie | KatalogAblehnung:
    """BR-KAT-05/BR-KAT-06: Der Anwendungsdienst überschreibt hier nur den
    Kategorie-Datensatz. Dass eine geänderte Leihdauer nur künftige
    Ausleihen betrifft (BR-KAT-05) und ein geändertes Wartungsintervall
    sofort für die nächste Prüfung gilt (BR-KAT-06), folgt daraus, *ohne*
    zusätzlichen Code hier: `Ausleihe.rueckgabefrist` wird bei der Ausgabe
    (UC-01) einmalig materialisiert und bleibt danach unverändert, und
    `Gegenstand.nutzungszaehler` wird beim nächsten Prüfabschluss (UC-04)
    stets gegen den *aktuellen* `Kategorie.wartungsintervall` verglichen.
    Siehe `katalog-pflegen.feature`, Szenarien zu BR-KAT-05/06."""
    bestehende = repo.find_by_id(kategorie_id)
    if bestehende is None:
        return KategorieNichtGefunden(kategorie_id)
    fehler = _kategorie_werte_pruefen(leihdauer_tage, wartungsintervall)
    if fehler is not None:
        return fehler
    geaendert = Kategorie(
        kategorie_id=kategorie_id,
        name=bestehende.name,
        leihdauer_tage=leihdauer_tage,
        wartungsintervall=wartungsintervall,
        einweisungspflichtig=einweisungspflichtig,
    )
    repo.update(geaendert)
    return geaendert


# --- Integration: Gegenstand ----------------------------------------------

def gegenstand_anlegen(
    gegenstand_repo: GegenstandRepository,
    kategorie_repo: KategorieRepository,
    inventarnummer: str,
    kategorie_id: str,
    wiederbeschaffungswert_cent: int,
) -> Gegenstand | KatalogAblehnung:
    if gegenstand_repo.find_by_inventarnummer(inventarnummer) is not None:
        return InventarnummerVergeben(inventarnummer)  # BR-KAT-01
    if kategorie_repo.find_by_id(kategorie_id) is None:
        return KategorieNichtGefunden(kategorie_id)
    fehler = _wiederbeschaffungswert_pruefen(wiederbeschaffungswert_cent)
    if fehler is not None:
        return fehler
    gegenstand = Gegenstand(
        inventarnummer=inventarnummer,
        kategorie_id=kategorie_id,
        zustand=GegenstandZustand.VERFUEGBAR,
        wiederbeschaffungswert_cent=wiederbeschaffungswert_cent,
        nutzungszaehler=0,
    )
    gegenstand_repo.insert(gegenstand)
    return gegenstand


def gegenstand_wert_aendern(
    gegenstand_repo: GegenstandRepository,
    inventarnummer: str,
    wiederbeschaffungswert_cent: int,
) -> Gegenstand | KatalogAblehnung:
    """BR-KAT-04: Die Kautionsberechnung verwendet ab sofort den neuen Wert
    — hier ist nichts weiter zu tun, weil die Kaution nicht am Gegenstand
    gespeichert, sondern bei Bedarf aus dem aktuellen
    `wiederbeschaffungswert_cent` neu berechnet wird (`domain/kaution.py`)."""
    bestehender = gegenstand_repo.find_by_inventarnummer(inventarnummer)
    if bestehender is None:
        return GegenstandNichtGefunden(inventarnummer)
    fehler = _wiederbeschaffungswert_pruefen(wiederbeschaffungswert_cent)
    if fehler is not None:
        return fehler
    geaendert = Gegenstand(
        inventarnummer=bestehender.inventarnummer,
        kategorie_id=bestehender.kategorie_id,
        zustand=bestehender.zustand,
        wiederbeschaffungswert_cent=wiederbeschaffungswert_cent,
        nutzungszaehler=bestehender.nutzungszaehler,
    )
    gegenstand_repo.update(geaendert)
    return geaendert
