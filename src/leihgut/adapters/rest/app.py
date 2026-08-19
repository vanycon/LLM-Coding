"""REST-Adapter (FastAPI) — enthält keine Fachlogik, ruft nur den
Anwendungskern auf (``05_building_block_view.adoc``).

Jeder Endpunkt prüft zuerst die Rolle (``rollen.py``, "zentrale
Rollenprüfung an der Systemgrenze", 08_concepts.adoc), bevor er den
Anwendungskern aufruft.
"""
import sqlite3

from fastapi import Depends, FastAPI, HTTPException

from leihgut.adapters.persistence.sqlite_ausleihe_repository import (
    SqliteAusleiheRepository,
)
from leihgut.adapters.persistence.sqlite_einweisung_repository import (
    SqliteEinweisungRepository,
)
from leihgut.adapters.persistence.sqlite_gegenstand_repository import (
    SqliteGegenstandRepository,
)
from leihgut.adapters.persistence.sqlite_kategorie_repository import (
    SqliteKategorieRepository,
)
from leihgut.adapters.persistence.sqlite_maengel_repository import (
    SqliteMaengelRepository,
)
from leihgut.adapters.persistence.sqlite_pruefabschluss_repository import (
    SqlitePruefabschlussRepository,
)
from leihgut.adapters.persistence.sqlite_vormerkung_repository import (
    SqliteVormerkungRepository,
)
from leihgut.adapters.rest.rollen import erfordere_rolle
from leihgut.adapters.rest.schemas import (
    EinweisungErfassenRequest,
    GegenstandAendernRequest,
    GegenstandAnlegenRequest,
    GegenstandAusgebenRequest,
    GegenstandZuruecknehmenRequest,
    KategorieAendernRequest,
    KategorieAnlegenRequest,
    PruefungAbschliessenRequest,
    VormerkungErfassenRequest,
)
from leihgut.adapters.system_clock import SystemClock
from leihgut.anwendungskern.ausleihe_service import (
    AusleiheNichtGefunden,
    AusleihlimitErreicht,
    BereitsZurueckgegeben,
    EinweisungFehlt,
    GegenstandNichtGefunden as AusgabeGegenstandNichtGefunden,
    GegenstandNichtVerfuegbar,
    MitgliedGesperrt,
    gegenstand_ausgeben,
    gegenstand_zuruecknehmen,
)
from leihgut.anwendungskern.pruefung_service import (
    AbzugUebersteigtKaution,
    AusleiheNichtGefunden as PruefungAusleiheNichtGefunden,
    NichtInPruefung,
    PruefabschlussErgebnis,
    pruefung_abschliessen,
)
from leihgut.anwendungskern.verlaengerung_service import (
    AusleiheNichtGefunden as VerlaengerungAusleiheNichtGefunden,
    AusleiheUeberfaellig,
    BereitsVerlaengert,
    MitgliedGesperrt as VerlaengerungMitgliedGesperrt,
    VormerkungOffen,
    ausleihe_verlaengern,
)
from leihgut.anwendungskern.einweisung_service import (
    BereitsWiderrufen,
    DuplikatEinweisung,
    EinweisungNichtGefunden,
    KategorieNichtGefunden as EinweisungKategorieNichtGefunden,
    einweisung_erfassen,
    einweisung_widerrufen,
)
from leihgut.anwendungskern.katalog_service import (
    GegenstandNichtGefunden,
    InventarnummerVergeben,
    KategorieNichtGefunden,
    WertUngueltig,
    gegenstand_anlegen,
    gegenstand_wert_aendern,
    kategorie_aendern,
    kategorie_anlegen,
)
from leihgut.anwendungskern.vormerkung_service import (
    DuplikatVormerkung,
    MitgliedGesperrt as VormerkungMitgliedGesperrt,
    VormerkungNichtGefunden,
    KategorieNichtGefunden as VormerkungKategorieNichtGefunden,
    vormerkung_erfassen,
    vormerkung_abrufen,
)
from leihgut.anwendungskern.verfuegbarkeit_service import (
    GegenstandNichtGefunden as VerfuegbarkeitNichtGefunden,
)
from leihgut.anwendungskern.verlust_service import (
    AusleiheNichtAktiv as VerlustAusleiheNichtAktiv,
    AusleiheNichtGefunden as VerlustAusleiheNichtGefunden,
    GegenstandNichtGefunden as VerlustGegenstandNichtGefunden,
    verlust_erfassen,
)
from leihgut.anwendungskern.verfuegbarkeit_service import verfuegbarkeit_pruefen
from leihgut.domain.ausleihe import Ausleihe
from leihgut.domain.einweisung import Einweisung
from leihgut.domain.gegenstand import Gegenstand
from leihgut.domain.kategorie import Kategorie
from leihgut.domain.vormerkung import Vormerkung
from leihgut.ports.clock import Clock

_KATALOG_ABLEHNUNG_STATUS = {
    InventarnummerVergeben: (409, "INVENTARNUMMER_VERGEBEN"),
    GegenstandNichtGefunden: (404, "GEGENSTAND_NICHT_GEFUNDEN"),
    KategorieNichtGefunden: (404, "KATEGORIE_NICHT_GEFUNDEN"),
    WertUngueltig: (422, "WERT_UNGUELTIG"),
}

_EINWEISUNG_ABLEHNUNG_STATUS = {
    EinweisungKategorieNichtGefunden: (404, "KATEGORIE_NICHT_GEFUNDEN"),
    DuplikatEinweisung: (409, "DUPLIKAT_EINWEISUNG"),
    EinweisungNichtGefunden: (404, "EINWEISUNG_NICHT_GEFUNDEN"),
    BereitsWiderrufen: (409, "BEREITS_WIDERRUFEN"),
}

_VORMERKUNG_ABLEHNUNG_STATUS = {
    VormerkungKategorieNichtGefunden: (404, "KATEGORIE_NICHT_GEFUNDEN"),
    VormerkungMitgliedGesperrt: (409, "MITGLIED_GESPERRT"),
    DuplikatVormerkung: (409, "DUPLIKAT_VORMERKUNG"),
    VormerkungNichtGefunden: (404, "VORMERKUNG_NICHT_GEFUNDEN"),
}

_AUSGABE_ABLEHNUNG_STATUS = {
    AusgabeGegenstandNichtGefunden: (404, "GEGENSTAND_NICHT_GEFUNDEN"),
    GegenstandNichtVerfuegbar: (409, "GEGENSTAND_NICHT_VERFUEGBAR"),
    MitgliedGesperrt: (409, "MITGLIED_GESPERRT"),
    AusleihlimitErreicht: (409, "AUSLEIHLIMIT_ERREICHT"),
    EinweisungFehlt: (409, "EINWEISUNG_FEHLT"),
}

_RUECKGABE_ABLEHNUNG_STATUS = {
    AusleiheNichtGefunden: (404, "AUSLEIHE_NICHT_GEFUNDEN"),
    BereitsZurueckgegeben: (409, "BEREITS_ZURUECKGEGEBEN"),
}

_PRUEFUNG_ABLEHNUNG_STATUS = {
    PruefungAusleiheNichtGefunden: (404, "AUSLEIHE_NICHT_GEFUNDEN"),
    NichtInPruefung: (409, "NICHT_IN_PRUEFUNG"),
    AbzugUebersteigtKaution: (422, "ABZUG_UEBERSTEIGT_KAUTION"),
}

_VERLAENGERUNG_ABLEHNUNG_STATUS = {
    VerlaengerungAusleiheNichtGefunden: (404, "AUSLEIHE_NICHT_GEFUNDEN"),
    AusleiheUeberfaellig: (409, "AUSLEIHE_UEBERFAELLIG"),
    VormerkungOffen: (409, "VORMERKUNG_OFFEN"),
    VerlaengerungMitgliedGesperrt: (409, "MITGLIED_GESPERRT"),
    BereitsVerlaengert: (409, "BEREITS_VERLAENGERT"),
}

_VERLUST_ABLEHNUNG_STATUS = {
    VerlustAusleiheNichtGefunden: (404, "AUSLEIHE_NICHT_GEFUNDEN"),
    VerlustAusleiheNichtAktiv: (409, "AUSLEIHE_NICHT_AKTIV"),
    VerlustGegenstandNichtGefunden: (404, "GEGENSTAND_NICHT_GEFUNDEN"),
}


def _katalog_ablehnung_zu_http(ablehnung) -> HTTPException:
    status_code, fehlercode = _KATALOG_ABLEHNUNG_STATUS[type(ablehnung)]
    return HTTPException(status_code=status_code, detail={"fehlercode": fehlercode})


def _einweisung_ablehnung_zu_http(ablehnung) -> HTTPException:
    status_code, fehlercode = _EINWEISUNG_ABLEHNUNG_STATUS[type(ablehnung)]
    return HTTPException(status_code=status_code, detail={"fehlercode": fehlercode})


def _vormerkung_ablehnung_zu_http(ablehnung) -> HTTPException:
    status_code, fehlercode = _VORMERKUNG_ABLEHNUNG_STATUS[type(ablehnung)]
    return HTTPException(status_code=status_code, detail={"fehlercode": fehlercode})


def _ausgabe_ablehnung_zu_http(ablehnung) -> HTTPException:
    status_code, fehlercode = _AUSGABE_ABLEHNUNG_STATUS[type(ablehnung)]
    return HTTPException(status_code=status_code, detail={"fehlercode": fehlercode})


def _rueckgabe_ablehnung_zu_http(ablehnung) -> HTTPException:
    status_code, fehlercode = _RUECKGABE_ABLEHNUNG_STATUS[type(ablehnung)]
    return HTTPException(status_code=status_code, detail={"fehlercode": fehlercode})


def _pruefung_ablehnung_zu_http(ablehnung) -> HTTPException:
    status_code, fehlercode = _PRUEFUNG_ABLEHNUNG_STATUS[type(ablehnung)]
    return HTTPException(status_code=status_code, detail={"fehlercode": fehlercode})


def _verlaengerung_ablehnung_zu_http(ablehnung) -> HTTPException:
    status_code, fehlercode = _VERLAENGERUNG_ABLEHNUNG_STATUS[type(ablehnung)]
    return HTTPException(status_code=status_code, detail={"fehlercode": fehlercode})


def _verlust_ablehnung_zu_http(ablehnung) -> HTTPException:
    status_code, fehlercode = _VERLUST_ABLEHNUNG_STATUS[type(ablehnung)]
    return HTTPException(status_code=status_code, detail={"fehlercode": fehlercode})


def _ausleihe_zu_dict(ausleihe: Ausleihe) -> dict:
    return {
        "ausleiheId": ausleihe.ausleihe_id,
        "gegenstandId": ausleihe.gegenstand_id,
        "mitgliedId": ausleihe.mitglied_id,
        "ausgabedatum": ausleihe.ausgabedatum,
        "rueckgabefrist": ausleihe.rueckgabefrist,
        "kautionCent": ausleihe.kaution_cent,
        "verlaengert": ausleihe.verlaengert,
        "zustand": ausleihe.zustand.value,
    }


def create_app(conn: sqlite3.Connection, clock: Clock | None = None) -> FastAPI:
    """Erzeugt die FastAPI-App mit einer festen SQLite-Verbindung.

    ``clock`` ist per Default `SystemClock` (ADR-006); Tests können einen
    Fake mit festem Datum einsetzen."""
    app = FastAPI(title="Leihgut REST-API")
    gegenstand_repo = SqliteGegenstandRepository(conn)
    kategorie_repo = SqliteKategorieRepository(conn)
    einweisung_repo = SqliteEinweisungRepository(conn)
    ausleihe_repo = SqliteAusleiheRepository(conn)
    maengel_repo = SqliteMaengelRepository(conn)
    pruefabschluss_repo = SqlitePruefabschlussRepository(conn)
    vormerkung_repo = SqliteVormerkungRepository(conn)
    clock = clock or SystemClock()

    wart_erforderlich = erfordere_rolle("wart")
    lesend_erlaubt = erfordere_rolle("thekendienst", "mitglied", "wart")
    thekendienst_erforderlich = erfordere_rolle("thekendienst")
    mitglied_erforderlich = erfordere_rolle("mitglied")

    @app.get("/gegenstaende/{inventarnummer}")
    def gegenstand_verfuegbarkeit(
        inventarnummer: str, _rolle: str = Depends(lesend_erlaubt)
    ):
        ergebnis = verfuegbarkeit_pruefen(gegenstand_repo, inventarnummer)
        if isinstance(ergebnis, VerfuegbarkeitNichtGefunden):
            raise HTTPException(
                status_code=404,
                detail={"fehlercode": "NICHT_GEFUNDEN"},
            )
        return {
            "inventarnummer": ergebnis.inventarnummer,
            "kategorieId": ergebnis.kategorie_id,
            "zustand": ergebnis.zustand.value,
        }

    @app.post("/kategorien", status_code=201)
    def kategorie_anlegen_endpoint(
        body: KategorieAnlegenRequest, _rolle: str = Depends(wart_erforderlich)
    ):
        ergebnis = kategorie_anlegen(
            kategorie_repo,
            body.kategorieId,
            body.name,
            body.leihdauerTage,
            body.wartungsintervall,
            body.einweisungspflichtig,
        )
        if isinstance(ergebnis, Kategorie):
            return {
                "kategorieId": ergebnis.kategorie_id,
                "name": ergebnis.name,
                "leihdauerTage": ergebnis.leihdauer_tage,
                "wartungsintervall": ergebnis.wartungsintervall,
                "einweisungspflichtig": ergebnis.einweisungspflichtig,
            }
        raise _katalog_ablehnung_zu_http(ergebnis)

    @app.put("/kategorien/{kategorieId}")
    def kategorie_aendern_endpoint(
        kategorieId: str,
        body: KategorieAendernRequest,
        _rolle: str = Depends(wart_erforderlich),
    ):
        ergebnis = kategorie_aendern(
            kategorie_repo,
            kategorieId,
            body.leihdauerTage,
            body.wartungsintervall,
            body.einweisungspflichtig,
        )
        if isinstance(ergebnis, Kategorie):
            return {
                "kategorieId": ergebnis.kategorie_id,
                "name": ergebnis.name,
                "leihdauerTage": ergebnis.leihdauer_tage,
                "wartungsintervall": ergebnis.wartungsintervall,
                "einweisungspflichtig": ergebnis.einweisungspflichtig,
            }
        raise _katalog_ablehnung_zu_http(ergebnis)

    @app.post("/gegenstaende", status_code=201)
    def gegenstand_anlegen_endpoint(
        body: GegenstandAnlegenRequest, _rolle: str = Depends(wart_erforderlich)
    ):
        ergebnis = gegenstand_anlegen(
            gegenstand_repo,
            kategorie_repo,
            body.inventarnummer,
            body.kategorieId,
            body.wiederbeschaffungswertCent,
        )
        if isinstance(ergebnis, Gegenstand):
            return {
                "inventarnummer": ergebnis.inventarnummer,
                "kategorieId": ergebnis.kategorie_id,
                "wiederbeschaffungswertCent": ergebnis.wiederbeschaffungswert_cent,
                "zustand": ergebnis.zustand.value,
            }
        raise _katalog_ablehnung_zu_http(ergebnis)

    @app.put("/gegenstaende/{inventarnummer}")
    def gegenstand_aendern_endpoint(
        inventarnummer: str,
        body: GegenstandAendernRequest,
        _rolle: str = Depends(wart_erforderlich),
    ):
        ergebnis = gegenstand_wert_aendern(
            gegenstand_repo, inventarnummer, body.wiederbeschaffungswertCent
        )
        if isinstance(ergebnis, Gegenstand):
            return {
                "inventarnummer": ergebnis.inventarnummer,
                "kategorieId": ergebnis.kategorie_id,
                "wiederbeschaffungswertCent": ergebnis.wiederbeschaffungswert_cent,
                "zustand": ergebnis.zustand.value,
            }
        raise _katalog_ablehnung_zu_http(ergebnis)

    @app.post("/einweisungen", status_code=201)
    def einweisung_erfassen_endpoint(
        body: EinweisungErfassenRequest, _rolle: str = Depends(wart_erforderlich)
    ):
        ergebnis = einweisung_erfassen(
            einweisung_repo, kategorie_repo, clock, body.mitgliedId, body.kategorieId
        )
        if not isinstance(ergebnis, Einweisung):
            raise _einweisung_ablehnung_zu_http(ergebnis)
        return {
            "einweisungId": ergebnis.einweisung_id,
            "mitgliedId": ergebnis.mitglied_id,
            "kategorieId": ergebnis.kategorie_id,
            "erstelltAm": ergebnis.erstellt_am,
        }

    @app.delete("/einweisungen/{einweisungId}", status_code=204)
    def einweisung_widerrufen_endpoint(
        einweisungId: str, _rolle: str = Depends(wart_erforderlich)
    ):
        ergebnis = einweisung_widerrufen(einweisung_repo, clock, einweisungId)
        if not isinstance(ergebnis, Einweisung):
            raise _einweisung_ablehnung_zu_http(ergebnis)
        return None

    @app.post("/vormerkungen", status_code=201)
    def vormerkung_erfassen_endpoint(
        body: VormerkungErfassenRequest, _rolle: str = Depends(mitglied_erforderlich)
    ):
        ergebnis = vormerkung_erfassen(
            vormerkung_repo, kategorie_repo, clock, body.mitgliedId, body.kategorieId,
            gesperrte_mitglieder=[]  # TODO: Stub bis mitglied_repo implementiert
        )
        if not isinstance(ergebnis, Vormerkung):
            raise _vormerkung_ablehnung_zu_http(ergebnis)
        return {
            "vormerkungId": ergebnis.vormerkung_id,
            "mitgliedId": ergebnis.mitglied_id,
            "kategorieId": ergebnis.kategorie_id,
            "erstelltAm": ergebnis.erstellt_am,
            "status": ergebnis.status.value,
            "reihenfolge": ergebnis.reihenfolge,
        }

    @app.get("/vormerkungen/{vormerkungId}")
    def vormerkung_abrufen_endpoint(
        vormerkungId: str, _rolle: str = Depends(lesend_erlaubt)
    ):
        ergebnis = vormerkung_abrufen(vormerkung_repo, vormerkungId)
        if not isinstance(ergebnis, Vormerkung):
            raise _vormerkung_ablehnung_zu_http(ergebnis)
        return {
            "vormerkungId": ergebnis.vormerkung_id,
            "mitgliedId": ergebnis.mitglied_id,
            "kategorieId": ergebnis.kategorie_id,
            "erstelltAm": ergebnis.erstellt_am,
            "status": ergebnis.status.value,
            "reihenfolge": ergebnis.reihenfolge,
        }

    @app.post("/gegenstaende/{inventarnummer}/ausgabe", status_code=201)
    def gegenstand_ausgeben_endpoint(
        inventarnummer: str,
        body: GegenstandAusgebenRequest,
        _rolle: str = Depends(thekendienst_erforderlich),
    ):
        ergebnis = gegenstand_ausgeben(
            gegenstand_repo,
            kategorie_repo,
            einweisung_repo,
            ausleihe_repo,
            clock,
            inventarnummer,
            body.mitgliedId,
        )
        if not isinstance(ergebnis, Ausleihe):
            raise _ausgabe_ablehnung_zu_http(ergebnis)
        return _ausleihe_zu_dict(ergebnis)

    @app.post("/ausleihen/{ausleiheId}/rueckgabe")
    def gegenstand_zuruecknehmen_endpoint(
        ausleiheId: str,
        body: GegenstandZuruecknehmenRequest,
        _rolle: str = Depends(thekendienst_erforderlich),
    ):
        ergebnis = gegenstand_zuruecknehmen(
            ausleihe_repo, gegenstand_repo, vormerkung_repo, ausleiheId, body.auffaelligkeiten
        )
        if not isinstance(ergebnis, Ausleihe):
            raise _rueckgabe_ablehnung_zu_http(ergebnis)
        return _ausleihe_zu_dict(ergebnis)

    @app.post("/ausleihen/{ausleiheId}/pruefprotokoll", status_code=201)
    def pruefung_abschliessen_endpoint(
        ausleiheId: str,
        body: PruefungAbschliessenRequest,
        _rolle: str = Depends(wart_erforderlich),
    ):
        ergebnis = pruefung_abschliessen(
            ausleihe_repo,
            gegenstand_repo,
            kategorie_repo,
            maengel_repo,
            pruefabschluss_repo,
            clock,
            ausleiheId,
            [m.beschreibung for m in body.neueMaengel],
            body.kautionsabzugCent,
            body.zielzustand,
        )
        if not isinstance(ergebnis, PruefabschlussErgebnis):
            raise _pruefung_ablehnung_zu_http(ergebnis)
        return {
            "pruefprotokollId": ergebnis.pruefprotokoll_id,
            "ausleiheId": ergebnis.ausleihe_id,
            "kautionsabzugCent": ergebnis.kautionsabzug_cent,
            "neuerGegenstandZustand": ergebnis.neuer_gegenstand_zustand.value,
        }

    @app.post("/ausleihen/{ausleiheId}/verlaengerung")
    def ausleihe_verlaengern_endpoint(
        ausleiheId: str,
        _rolle: str = Depends(thekendienst_erforderlich),
    ):
        ergebnis = ausleihe_verlaengern(
            ausleihe_repo, kategorie_repo, gegenstand_repo, clock, ausleiheId
        )
        if not isinstance(ergebnis, Ausleihe):
            raise _verlaengerung_ablehnung_zu_http(ergebnis)
        return _ausleihe_zu_dict(ergebnis)

    @app.post("/ausleihen/{ausleiheId}/verlust", status_code=201)
    def verlust_erfassen_endpoint(
        ausleiheId: str,
        rolle: str = Depends(wart_erforderlich),
    ):
        ergebnis = verlust_erfassen(
            conn, ausleihe_repo, gegenstand_repo, clock, ausleiheId, rolle
        )
        if not isinstance(ergebnis, Ausleihe):
            raise _verlust_ablehnung_zu_http(ergebnis)
        return _ausleihe_zu_dict(ergebnis)

    return app

