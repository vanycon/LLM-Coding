"""Anwendungsdienst für UC-04 (Prüfung abschließen) / SI-04.

IOSP: `_pruefung_pruefen` ist die reine Operation (BR-KAU-02-Prüfung, keine
Ports); `pruefung_abschliessen` ist die Integration (Repository-Aufrufe in
der von SI-04 vorgegebenen Prüfreihenfolge: Ausleihe-Existenz → Gegenstand
"in Prüfung" → Kautionsabzug ≤ hinterlegte Kaution).
"""
import uuid
from dataclasses import dataclass

from leihgut.domain.audit_log import AuditLogEintrag
from leihgut.domain.ausleihe import Ausleihe, AusleiheZustand
from leihgut.domain.gegenstand import Gegenstand, GegenstandZustand
from leihgut.domain.kautionsbewegung import Kautionsbewegung, KautionsbewegungArt
from leihgut.domain.maengel import MaengelEintrag
from leihgut.domain.pruefprotokoll import Pruefprotokoll
from leihgut.ports.ausleihe_repository import AusleiheRepository
from leihgut.ports.clock import Clock
from leihgut.ports.gegenstand_repository import GegenstandRepository
from leihgut.ports.kategorie_repository import KategorieRepository
from leihgut.ports.maengel_repository import MaengelRepository
from leihgut.ports.pruefabschluss_repository import PruefabschlussRepository


@dataclass(frozen=True)
class AusleiheNichtGefunden:
    """SI-04-Ablehnung: `404 AUSLEIHE_NICHT_GEFUNDEN`."""

    ausleihe_id: str


@dataclass(frozen=True)
class NichtInPruefung:
    """SI-04-Ablehnung: `409 NICHT_IN_PRUEFUNG` — der zur Ausleihe gehörige
    Gegenstand ist nicht im Zustand `in_pruefung` (Voraussetzung: UC-03
    wurde bereits durchlaufen)."""

    ausleihe_id: str


@dataclass(frozen=True)
class AbzugUebersteigtKaution:
    """SI-04-Ablehnung: `422 ABZUG_UEBERSTEIGT_KAUTION` (BR-KAU-02)."""

    ausleihe_id: str
    kautionsabzug_cent: int
    hinterlegte_kaution_cent: int


PruefabschlussAblehnung = (
    AusleiheNichtGefunden | NichtInPruefung | AbzugUebersteigtKaution
)


@dataclass(frozen=True)
class PruefabschlussErgebnis:
    """Antwortmodell für SI-04: `{pruefprotokollId, ausleiheId,
    kautionsabzugCent, neuerGegenstandZustand}`."""

    pruefprotokoll_id: str
    ausleihe_id: str
    kautionsabzug_cent: int
    neuer_gegenstand_zustand: GegenstandZustand


# --- Operation: reine Validierung, kein Port-Zugriff --------------------

def _pruefung_pruefen(
    ausleihe_id: str,
    gegenstand_zustand: GegenstandZustand | None,
    kaution_cent: int,
    kautionsabzug_cent: int,
) -> PruefabschlussAblehnung | None:
    """Prüfreihenfolge exakt wie in SI-04 dokumentiert: Gegenstand "in
    Prüfung" → Kautionsabzug ≤ hinterlegte Kaution (BR-KAU-02)."""
    if gegenstand_zustand != GegenstandZustand.IN_PRUEFUNG:
        return NichtInPruefung(ausleihe_id)
    if kautionsabzug_cent > kaution_cent:
        return AbzugUebersteigtKaution(ausleihe_id, kautionsabzug_cent, kaution_cent)
    return None


def _folgezustand_bestimmen(
    zielzustand: str, nutzungszaehler_neu: int, wartungsintervall: int
) -> GegenstandZustand:
    """SI-04, Verarbeitungsschritt 5: `ausgemustert` (falls vom Wart
    angegeben) schlägt `wartungsfaellig` (BR-WAR-02), das wiederum
    `verfuegbar` schlägt. Die Vergabe einer Reservierung bei `verfuegbar`
    (BR-VOR-03) ist bewusst nicht Teil dieser Story (siehe Analyse in
    epic-b-pruefung-kaution.adoc: Vormerkung existiert erst ab EPIC-E)."""
    if zielzustand == "ausgemustert":
        return GegenstandZustand.AUSGEMUSTERT
    if nutzungszaehler_neu >= wartungsintervall:
        return GegenstandZustand.WARTUNGSFAELLIG
    return GegenstandZustand.VERFUEGBAR


# --- Integration: Prüfung abschließen (UC-04) ---------------------------

def pruefung_abschliessen(
    ausleihe_repo: AusleiheRepository,
    gegenstand_repo: GegenstandRepository,
    kategorie_repo: KategorieRepository,
    maengel_repo: MaengelRepository,
    pruefabschluss_repo: PruefabschlussRepository,
    clock: Clock,
    ausleihe_id: str,
    neue_maengel_beschreibungen: list[str],
    kautionsabzug_cent: int,
    zielzustand_eingabe: str,
    ausloeser_rolle: str = "wart",
) -> PruefabschlussErgebnis | PruefabschlussAblehnung:
    ausleihe = ausleihe_repo.find_by_id(ausleihe_id)
    if ausleihe is None:
        return AusleiheNichtGefunden(ausleihe_id)

    gegenstand = gegenstand_repo.find_by_inventarnummer(ausleihe.gegenstand_id)
    ablehnung = _pruefung_pruefen(
        ausleihe_id,
        gegenstand.zustand if gegenstand is not None else None,
        ausleihe.kaution_cent,
        kautionsabzug_cent,
    )
    if ablehnung is not None:
        return ablehnung

    jetzt = clock.jetzt()
    kategorie = kategorie_repo.find_by_id(gegenstand.kategorie_id)

    # BR-RUP-05: nur wirklich neue Schäden der Ausleihe zurechnen und der
    # Mängelliste hinzufügen.
    bekannte_beschreibungen = {
        eintrag.beschreibung
        for eintrag in maengel_repo.find_by_gegenstand(gegenstand.inventarnummer)
    }
    pruefprotokoll_id = str(uuid.uuid4())
    neue_maengel = [
        MaengelEintrag(
            maengel_id=str(uuid.uuid4()),
            gegenstand_id=gegenstand.inventarnummer,
            beschreibung=beschreibung,
            festgestellt_in_pruefprotokoll_id=pruefprotokoll_id,
        )
        for beschreibung in neue_maengel_beschreibungen
        if beschreibung not in bekannte_beschreibungen
    ]

    nutzungszaehler_neu = gegenstand.nutzungszaehler + 1  # BR-WAR-01
    folgezustand = _folgezustand_bestimmen(
        zielzustand_eingabe, nutzungszaehler_neu, kategorie.wartungsintervall
    )

    pruefprotokoll = Pruefprotokoll(
        pruefprotokoll_id=pruefprotokoll_id,
        ausleihe_id=ausleihe_id,
        kautionsabzug_cent=kautionsabzug_cent,
        zielzustand=folgezustand.value,
        erstellt_am=jetzt,
        neue_maengel_ids=[m.maengel_id for m in neue_maengel],
    )

    freigabe_cent = ausleihe.kaution_cent - kautionsabzug_cent
    kautionsbewegungen = [
        Kautionsbewegung(
            bewegung_id=str(uuid.uuid4()),
            ausleihe_id=ausleihe_id,
            art=KautionsbewegungArt.FREIGABE,
            betrag_cent=freigabe_cent,
            zeitstempel=jetzt,
            ausloeser=ausloeser_rolle,
        )
    ]
    if kautionsabzug_cent > 0:
        kautionsbewegungen.append(
            Kautionsbewegung(
                bewegung_id=str(uuid.uuid4()),
                ausleihe_id=ausleihe_id,
                art=KautionsbewegungArt.ABZUG,
                betrag_cent=kautionsabzug_cent,
                zeitstempel=jetzt,
                ausloeser=ausloeser_rolle,
            )
        )

    aktualisierte_ausleihe = Ausleihe(
        ausleihe_id=ausleihe.ausleihe_id,
        gegenstand_id=ausleihe.gegenstand_id,
        mitglied_id=ausleihe.mitglied_id,
        ausgabedatum=ausleihe.ausgabedatum,
        rueckgabefrist=ausleihe.rueckgabefrist,
        kaution_cent=ausleihe.kaution_cent,
        verlaengert=ausleihe.verlaengert,
        zustand=AusleiheZustand.ABGESCHLOSSEN,  # BR-RUP-04
        rueckgabe_auffaelligkeiten=ausleihe.rueckgabe_auffaelligkeiten,
    )
    aktualisierter_gegenstand = Gegenstand(
        inventarnummer=gegenstand.inventarnummer,
        kategorie_id=gegenstand.kategorie_id,
        zustand=folgezustand,
        wiederbeschaffungswert_cent=gegenstand.wiederbeschaffungswert_cent,
        nutzungszaehler=nutzungszaehler_neu,
    )
    audit_eintrag = AuditLogEintrag(
        zeitstempel=jetzt,
        aggregat="ausleihe",
        aggregat_id=ausleihe_id,
        ereignisart="pruefung_abgeschlossen",
        rolle=ausloeser_rolle,
        werte_vorher="zustand=zurueckgegeben,gegenstand_zustand=in_pruefung",
        werte_nachher=(
            f"zustand=abgeschlossen,gegenstand_zustand={folgezustand.value},"
            f"kautionsabzug_cent={kautionsabzug_cent}"
        ),
    )

    pruefabschluss_repo.abschliessen(
        aktualisierte_ausleihe,
        aktualisierter_gegenstand,
        pruefprotokoll,
        neue_maengel,
        kautionsbewegungen,
        audit_eintrag,
    )

    return PruefabschlussErgebnis(
        pruefprotokoll_id=pruefprotokoll_id,
        ausleihe_id=ausleihe_id,
        kautionsabzug_cent=kautionsabzug_cent,
        neuer_gegenstand_zustand=folgezustand,
    )
