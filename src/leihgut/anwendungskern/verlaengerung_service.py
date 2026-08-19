"""Anwendungsdienst für UC-02 (Ausleihe verlängern) / SI-02.

IOSP: `_verlaengerung_validieren` ist die reine Operation (Datumsprüfung,
Zustandsprüfung); `ausleihe_verlaengern` ist die Integration
(Repository-Aufrufe gemäss SI-02 Validierungsreihenfolge).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from leihgut.domain.ausleihe import Ausleihe, AusleiheZustand
from leihgut.ports.ausleihe_repository import AusleiheRepository
from leihgut.ports.clock import Clock
from leihgut.ports.kategorie_repository import KategorieRepository
from leihgut.ports.gegenstand_repository import GegenstandRepository


@dataclass(frozen=True)
class AusleiheNichtGefunden:
    """SI-02-Ablehnung: `404 AUSLEIHE_NICHT_GEFUNDEN`."""

    ausleihe_id: str


@dataclass(frozen=True)
class AusleiheUeberfaellig:
    """SI-02-Ablehnung: `409 AUSLEIHE_UEBERFAELLIG` (BR-AUS-07)."""

    ausleihe_id: str


@dataclass(frozen=True)
class VormerkungOffen:
    """SI-02-Ablehnung: `409 VORMERKUNG_OFFEN` (BR-AUS-07).
    
    DEFERRED zu EPIC-E: Derzeit nicht implementierbar, da Vormerkungen/
    Reservierungen noch nicht existieren. Wird mit EPIC-E echte Prüfung.
    """

    ausleihe_id: str


@dataclass(frozen=True)
class MitgliedGesperrt:
    """SI-02-Ablehnung: `409 MITGLIED_GESPERRT` (BR-AUS-08)."""

    ausleihe_id: str


@dataclass(frozen=True)
class BereitsVerlaengert:
    """SI-02-Ablehnung: `409 BEREITS_VERLAENGERT` (BR-AUS-06)."""

    ausleihe_id: str


VerlaengerungAblehnung = (
    AusleiheNichtGefunden
    | AusleiheUeberfaellig
    | VormerkungOffen
    | MitgliedGesperrt
    | BereitsVerlaengert
)


# --- Operation: reine Validierung, kein Port-Zugriff ----------------

def _verlaengerung_validieren(
    ausleihe_zustand: AusleiheZustand | None,
    rueckgabefrist_str: str | None,
    heute: str,
    mitglied_gesperrt: bool,
    verlaengert: bool,
) -> VerlaengerungAblehnung | None:
    """Validierung exakt wie in SI-02 dokumentiert.
    
    Diese Operation prüft nur Regeln, die keine neuen Daten benötigen
    (Datumsprüfung, Zustandsprüfung). Das Vormerkung-Feld wird vom
    Aufrufer geprüft.
    """
    # Prüfe: Ausleihe ist aktiv
    if ausleihe_zustand != AusleiheZustand.AKTIV:
        return None  # wird vom Aufrufer mit AUSLEIHE_NICHT_GEFUNDEN gefüllt

    # Prüfe: nicht überfällig (BR-AUS-07)
    if rueckgabefrist_str is not None and rueckgabefrist_str < heute:
        # heute ist im Format "YYYY-MM-DD", string comparison works
        return None  # wird vom Aufrufer mit AUSLEIHE_UEBERFAELLIG gefüllt

    # Prüfe: Mitglied nicht gesperrt (BR-AUS-08)
    if mitglied_gesperrt:
        return None  # wird vom Aufrufer mit MITGLIED_GESPERRT gefüllt

    # Prüfe: noch nicht verlängert (BR-AUS-06)
    if verlaengert:
        return None  # wird vom Aufrufer mit BEREITS_VERLAENGERT gefüllt

    return None


# --- Integration: Ausleihe verlängern (UC-02) -------------------------

def ausleihe_verlaengern(
    ausleihe_repo: AusleiheRepository,
    kategorie_repo: KategorieRepository,
    gegenstand_repo: GegenstandRepository,
    clock: Clock,
    ausleihe_id: str,
) -> Ausleihe | VerlaengerungAblehnung:
    """Ausleihe verlängern (UC-02 / SI-02).
    
    Validierungsreihenfolge exakt wie in SI-02:
    1. Ausleihe existiert & aktiv (404)
    2. Nicht überfällig (409)
    3. Keine Vormerkung offen (409) — DEFERRED
    4. Mitglied nicht gesperrt (409)
    5. Noch nicht verlängert (409)
    """
    ausleihe = ausleihe_repo.find_by_id(ausleihe_id)
    if ausleihe is None or ausleihe.zustand != AusleiheZustand.AKTIV:
        return AusleiheNichtGefunden(ausleihe_id)

    heute = clock.jetzt().strftime("%Y-%m-%d")

    # Prüfe: nicht überfällig (BR-AUS-07)
    if ausleihe.rueckgabefrist < heute:
        return AusleiheUeberfaellig(ausleihe_id)

    # Prüfe: Keine offene Vormerkung (BR-AUS-07, DEFERRED zu EPIC-E)
    # Für jetzt: Stub-Implementierung — würde mit EPIC-E geprüft
    # (Logik: kategorie.reservierungen_offen > 0, aber Feld existiert noch nicht)
    # return VormerkungOffen(ausleihe_id)  # UNCOMMENT mit EPIC-E

    # Prüfe: Mitglied nicht gesperrt (BR-AUS-08)
    if ausleihe.mitglied_gesperrt:
        return MitgliedGesperrt(ausleihe_id)

    # Prüfe: noch nicht verlängert (BR-AUS-06)
    if ausleihe.verlaengert:
        return BereitsVerlaengert(ausleihe_id)

    # Lade Gegenstand, um kategorie_id zu bekommen
    gegenstand = gegenstand_repo.find_by_inventarnummer(ausleihe.gegenstand_id)
    if gegenstand is None:
        # sollte nicht vorkommen (FK-Constraint), aber safety-check
        return AusleiheNichtGefunden(ausleihe_id)
    
    kategorie = kategorie_repo.find_by_id(gegenstand.kategorie_id)
    if kategorie is None:
        # sollte nicht vorkommen (FK-Constraint), aber safety-check
        return AusleiheNichtGefunden(ausleihe_id)

    # Berechne neue Rückgabefrist (BR-AUS-06)
    # rueckgabefrist aktuell: YYYY-MM-DD (string)
    rueckgabefrist_date = datetime.strptime(
        ausleihe.rueckgabefrist, "%Y-%m-%d"
    )
    neue_rueckgabefrist_date = rueckgabefrist_date + timedelta(
        days=kategorie.leihdauer_tage
    )
    neue_rueckgabefrist = neue_rueckgabefrist_date.strftime("%Y-%m-%d")

    # Aktualisiere Ausleihe (BR-AUS-06, BR-AUS-09: Kaution unverändert)
    verlaengerte_ausleihe = Ausleihe(
        ausleihe_id=ausleihe.ausleihe_id,
        gegenstand_id=ausleihe.gegenstand_id,
        mitglied_id=ausleihe.mitglied_id,
        ausgabedatum=ausleihe.ausgabedatum,
        rueckgabefrist=neue_rueckgabefrist,
        kaution_cent=ausleihe.kaution_cent,  # BR-AUS-09: unverändert
        verlaengert=True,  # BR-AUS-06
        zustand=AusleiheZustand.AKTIV,
        rueckgabe_auffaelligkeiten=ausleihe.rueckgabe_auffaelligkeiten,
    )

    ausleihe_repo.update(verlaengerte_ausleihe)
    return verlaengerte_ausleihe
