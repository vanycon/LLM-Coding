"""REST-Adapter (FastAPI) — enthält keine Fachlogik, ruft nur den
Anwendungskern auf (``05_building_block_view.adoc``).

Skeleton-01 verzichtet bewusst auf Rollenprüfung, Connection-Pooling und
vollständige SI-10-Fehlercode-Abdeckung — Zweck dieses ersten Schnitts ist
der Nachweis, dass REST-Adapter, Anwendungskern und Persistenz-Adapter
zusammenspielen, nicht fachlicher Vollumfang (siehe
``src/docs/implementation/backlog.adoc``, Skeleton-01).
"""
import sqlite3

from fastapi import FastAPI, HTTPException

from leihgut.adapters.persistence.sqlite_gegenstand_repository import (
    SqliteGegenstandRepository,
)
from leihgut.anwendungskern.verfuegbarkeit_service import (
    GegenstandNichtGefunden,
    verfuegbarkeit_pruefen,
)


def create_app(conn: sqlite3.Connection) -> FastAPI:
    """Erzeugt die FastAPI-App mit einer festen SQLite-Verbindung."""
    app = FastAPI(title="Leihgut REST-API")
    repo = SqliteGegenstandRepository(conn)

    @app.get("/gegenstaende/{inventarnummer}")
    def gegenstand_verfuegbarkeit(inventarnummer: str):
        ergebnis = verfuegbarkeit_pruefen(repo, inventarnummer)
        if isinstance(ergebnis, GegenstandNichtGefunden):
            raise HTTPException(
                status_code=404,
                detail={"fehlercode": "NICHT_GEFUNDEN"},
            )
        return {
            "inventarnummer": ergebnis.inventarnummer,
            "kategorieId": ergebnis.kategorie_id,
            "zustand": ergebnis.zustand.value,
        }

    return app
