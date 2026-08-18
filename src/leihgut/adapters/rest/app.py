"""REST-Adapter (FastAPI) — enthält keine Fachlogik, ruft nur den
Anwendungskern auf (``05_building_block_view.adoc``).

Jeder Endpunkt prüft zuerst die Rolle (``rollen.py``, "zentrale
Rollenprüfung an der Systemgrenze", 08_concepts.adoc), bevor er den
Anwendungskern aufruft.
"""
import sqlite3

from fastapi import Depends, FastAPI, HTTPException

from leihgut.adapters.persistence.sqlite_gegenstand_repository import (
    SqliteGegenstandRepository,
)
from leihgut.adapters.persistence.sqlite_kategorie_repository import (
    SqliteKategorieRepository,
)
from leihgut.adapters.rest.rollen import erfordere_rolle
from leihgut.adapters.rest.schemas import (
    GegenstandAendernRequest,
    GegenstandAnlegenRequest,
    KategorieAendernRequest,
    KategorieAnlegenRequest,
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
from leihgut.anwendungskern.verfuegbarkeit_service import (
    GegenstandNichtGefunden as VerfuegbarkeitNichtGefunden,
)
from leihgut.anwendungskern.verfuegbarkeit_service import verfuegbarkeit_pruefen
from leihgut.domain.gegenstand import Gegenstand
from leihgut.domain.kategorie import Kategorie

_KATALOG_ABLEHNUNG_STATUS = {
    InventarnummerVergeben: (409, "INVENTARNUMMER_VERGEBEN"),
    GegenstandNichtGefunden: (404, "GEGENSTAND_NICHT_GEFUNDEN"),
    KategorieNichtGefunden: (404, "KATEGORIE_NICHT_GEFUNDEN"),
    WertUngueltig: (422, "WERT_UNGUELTIG"),
}


def _katalog_ablehnung_zu_http(ablehnung) -> HTTPException:
    status_code, fehlercode = _KATALOG_ABLEHNUNG_STATUS[type(ablehnung)]
    return HTTPException(status_code=status_code, detail={"fehlercode": fehlercode})


def create_app(conn: sqlite3.Connection) -> FastAPI:
    """Erzeugt die FastAPI-App mit einer festen SQLite-Verbindung."""
    app = FastAPI(title="Leihgut REST-API")
    gegenstand_repo = SqliteGegenstandRepository(conn)
    kategorie_repo = SqliteKategorieRepository(conn)

    wart_erforderlich = erfordere_rolle("wart")
    lesend_erlaubt = erfordere_rolle("thekendienst", "mitglied", "wart")

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

    return app

