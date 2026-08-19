"""Anwendungsdienst für UC-01 (Gegenstand ausgeben) und UC-03 (Gegenstand
zurücknehmen) / SI-01, SI-03.

IOSP: `_ausgabe_pruefen` ist die reine Operation (keine Ports, nur
Domänenwerte) und wird isoliert getestet; `gegenstand_ausgeben` ist die
Integration (Repository-Aufrufe in der in SI-01/UC-01 vorgegebenen
Prüfreihenfolge). Siehe `08_concepts.adoc`, Abschnitt Test.
"""
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from leihgut.domain.ausleihe import Ausleihe, AusleiheZustand
from leihgut.domain.gegenstand import Gegenstand, GegenstandZustand
from leihgut.domain.kategorie import Kategorie
from leihgut.domain.kaution import kaution_berechnen
from leihgut.ports.ausleihe_repository import (
    AusleiheRepository,
    NebenlaeufigeAusgabeAbgelehnt,
)
from leihgut.ports.clock import Clock
from leihgut.ports.einweisung_repository import EinweisungRepository
from leihgut.ports.gegenstand_repository import GegenstandRepository
from leihgut.ports.kategorie_repository import KategorieRepository
from leihgut.ports.vormerkung_repository import VormerkungRepository
from leihgut.anwendungskern.vormerkung_service import vormerkungs_verwalten_nach_rueckgabe

MAX_AUSLEIHEN_JE_MITGLIED = 3  # BR-AUS-02


@dataclass(frozen=True)
class GegenstandNichtGefunden:
    """SI-01-Ablehnung: `404 GEGENSTAND_NICHT_GEFUNDEN`."""

    inventarnummer: str


@dataclass(frozen=True)
class GegenstandNichtVerfuegbar:
    """SI-01-Ablehnung: `409 GEGENSTAND_NICHT_VERFUEGBAR` (BR-AUS-01).

    Umfasst auch den Fall `zustand == reserviert`: die Prüfung, ob die
    Reservierung für *dieses* Mitglied gilt, setzt die Vormerkung/
    Reservierung aus EPIC-E voraus und wird erst dort ergänzt (siehe
    Analyse in `epic-a-ausleihe-kernprozess.adoc`, User Story A1) — bis
    dahin gilt jeder nicht-verfügbare Gegenstand konservativ als nicht
    ausgebbar."""

    inventarnummer: str


@dataclass(frozen=True)
class MitgliedGesperrt:
    """SI-01-Ablehnung: `409 MITGLIED_GESPERRT` (BR-AUS-03)."""

    mitglied_id: str


@dataclass(frozen=True)
class AusleihlimitErreicht:
    """SI-01-Ablehnung: `409 AUSLEIHLIMIT_ERREICHT` (BR-AUS-02)."""

    mitglied_id: str


@dataclass(frozen=True)
class EinweisungFehlt:
    """SI-01-Ablehnung: `409 EINWEISUNG_FEHLT` (BR-AUS-04)."""

    mitglied_id: str
    kategorie_id: str


AusgabeAblehnung = (
    GegenstandNichtGefunden
    | GegenstandNichtVerfuegbar
    | MitgliedGesperrt
    | AusleihlimitErreicht
    | EinweisungFehlt
)


@dataclass(frozen=True)
class AusleiheNichtGefunden:
    """SI-03-Ablehnung: `404 AUSLEIHE_NICHT_GEFUNDEN`."""

    ausleihe_id: str


@dataclass(frozen=True)
class BereitsZurueckgegeben:
    """SI-03-Ablehnung: `409 BEREITS_ZURUECKGEGEBEN` — deckt sowohl bereits
    zurückgegebene als auch bereits abgeschlossene Ausleihen ab (SI-03:
    "weder zurückgegeben noch abgeschlossen")."""

    ausleihe_id: str


RueckgabeAblehnung = AusleiheNichtGefunden | BereitsZurueckgegeben


# --- Operation: reine Validierung, kein Port-Zugriff --------------------

def _ausgabe_pruefen(
    gegenstand: Gegenstand,
    kategorie: Kategorie,
    mitglied_id: str,
    mitglied_gesperrt: bool,
    offene_ausleihen_anzahl: int,
    einweisung_gueltig: bool,
) -> AusgabeAblehnung | None:
    """Prüfreihenfolge exakt wie in SI-01/UC-01 dokumentiert: Verfügbarkeit
    → Sperre → Ausleihlimit → Einweisung."""
    if gegenstand.zustand != GegenstandZustand.VERFUEGBAR:
        return GegenstandNichtVerfuegbar(gegenstand.inventarnummer)  # BR-AUS-01
    if mitglied_gesperrt:
        return MitgliedGesperrt(mitglied_id)  # BR-AUS-03
    if offene_ausleihen_anzahl >= MAX_AUSLEIHEN_JE_MITGLIED:
        return AusleihlimitErreicht(mitglied_id)  # BR-AUS-02
    if kategorie.einweisungspflichtig and not einweisung_gueltig:
        return EinweisungFehlt(mitglied_id, kategorie.kategorie_id)  # BR-AUS-04
    return None


# --- Integration: Gegenstand ausgeben (UC-01) ---------------------------

def gegenstand_ausgeben(
    gegenstand_repo: GegenstandRepository,
    kategorie_repo: KategorieRepository,
    einweisung_repo: EinweisungRepository,
    ausleihe_repo: AusleiheRepository,
    clock: Clock,
    inventarnummer: str,
    mitglied_id: str,
) -> Ausleihe | AusgabeAblehnung:
    gegenstand = gegenstand_repo.find_by_inventarnummer(inventarnummer)
    if gegenstand is None:
        return GegenstandNichtGefunden(inventarnummer)
    kategorie = kategorie_repo.find_by_id(gegenstand.kategorie_id)

    offene_ausleihen = ausleihe_repo.finde_offene_fuer_mitglied(mitglied_id)
    heute = clock.jetzt()[:10]
    mitglied_gesperrt = any(a.ist_ueberfaellig(heute) for a in offene_ausleihen)
    einweisung_gueltig = (
        einweisung_repo.find_gueltige_je_mitglied_kategorie(mitglied_id, gegenstand.kategorie_id)
        is not None
    )

    ablehnung = _ausgabe_pruefen(
        gegenstand,
        kategorie,
        mitglied_id,
        mitglied_gesperrt,
        len(offene_ausleihen),
        einweisung_gueltig,
    )
    if ablehnung is not None:
        return ablehnung

    ausgabedatum = heute
    rueckgabefrist = (
        date.fromisoformat(ausgabedatum) + timedelta(days=kategorie.leihdauer_tage)
    ).isoformat()
    kaution_cent = kaution_berechnen(gegenstand.wiederbeschaffungswert_cent)

    ausleihe = Ausleihe(
        ausleihe_id=str(uuid.uuid4()),
        gegenstand_id=inventarnummer,
        mitglied_id=mitglied_id,
        ausgabedatum=ausgabedatum,
        rueckgabefrist=rueckgabefrist,
        kaution_cent=kaution_cent,
        verlaengert=False,
        zustand=AusleiheZustand.AKTIV,
    )
    try:
        ausleihe_repo.insert(ausleihe)
    except NebenlaeufigeAusgabeAbgelehnt:
        # ADR-007: die Lese-Prüfung oben hat "verfügbar" gesehen, eine
        # parallele Anfrage hat die Ausgabe aber zuerst abgeschlossen.
        return GegenstandNichtVerfuegbar(inventarnummer)
    gegenstand_repo.update(
        Gegenstand(
            inventarnummer=gegenstand.inventarnummer,
            kategorie_id=gegenstand.kategorie_id,
            zustand=GegenstandZustand.AUSGELIEHEN,
            wiederbeschaffungswert_cent=gegenstand.wiederbeschaffungswert_cent,
            nutzungszaehler=gegenstand.nutzungszaehler,
        )
    )
    return ausleihe


# --- Integration: Gegenstand zurücknehmen (UC-03) -----------------------

def gegenstand_zuruecknehmen(
    ausleihe_repo: AusleiheRepository,
    gegenstand_repo: GegenstandRepository,
    vormerkung_repo: VormerkungRepository,
    ausleihe_id: str,
    auffaelligkeiten: str | None = None,
) -> Ausleihe | RueckgabeAblehnung:
    bestehende = ausleihe_repo.find_by_id(ausleihe_id)
    if bestehende is None:
        return AusleiheNichtGefunden(ausleihe_id)
    if bestehende.zustand != AusleiheZustand.AKTIV:
        return BereitsZurueckgegeben(ausleihe_id)  # BR-RUP: SI-03

    geaenderte_ausleihe = Ausleihe(
        ausleihe_id=bestehende.ausleihe_id,
        gegenstand_id=bestehende.gegenstand_id,
        mitglied_id=bestehende.mitglied_id,
        ausgabedatum=bestehende.ausgabedatum,
        rueckgabefrist=bestehende.rueckgabefrist,
        kaution_cent=bestehende.kaution_cent,
        verlaengert=bestehende.verlaengert,
        zustand=AusleiheZustand.ZURUECKGEGEBEN,
        rueckgabe_auffaelligkeiten=auffaelligkeiten,
    )
    ausleihe_repo.update(geaenderte_ausleihe)

    gegenstand = gegenstand_repo.find_by_inventarnummer(bestehende.gegenstand_id)
    gegenstand_repo.update(
        Gegenstand(
            inventarnummer=gegenstand.inventarnummer,
            kategorie_id=gegenstand.kategorie_id,
            zustand=GegenstandZustand.IN_PRUEFUNG,  # BR-RUP-01
            wiederbeschaffungswert_cent=gegenstand.wiederbeschaffungswert_cent,
            nutzungszaehler=gegenstand.nutzungszaehler,
        )
    )
    
    # Nach erfolgreicher Rückgabe: Erste offene Vormerkung automatisch absagen (UC-05 Integration)
    vormerkungs_verwalten_nach_rueckgabe(vormerkung_repo, gegenstand.kategorie_id)
    
    return geaenderte_ausleihe
