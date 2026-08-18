"""SQLite-Persistenz-Adapter (ADR-004: eine einzige SQLite-Datei)."""
import sqlite3
from pathlib import Path

from leihgut.domain.gegenstand import Gegenstand, GegenstandZustand

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def create_connection(db_path: str) -> sqlite3.Connection:
    """Öffnet eine SQLite-Verbindung und legt das Schema an, falls es fehlt.

    ``db_path`` kann ein Dateipfad oder ``":memory:"`` sein (Service-Level-
    Tests nutzen ``":memory:"``, siehe ``08_concepts.adoc``, Abschnitt Test).
    """
    # check_same_thread=False: FastAPI/uvicorn bedient synchrone
    # Endpunkte in Worker-Threads; die Ein-Prozess/Ein-Schreiber-Garantie
    # (ADR-004/ADR-005) kommt weiterhin aus BEGIN IMMEDIATE (ADR-007) und
    # dem Umstand, dass nur der REST-Prozess schreibt, nicht aus
    # Thread-Affinität der Connection.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    return conn


class SqliteGegenstandRepository:
    """Implementiert den Port ``GegenstandRepository`` (nur der für
    Skeleton-01 benötigte Ausschnitt: Lesen nach Inventarnummer)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def find_by_inventarnummer(self, inventarnummer: str) -> Gegenstand | None:
        row = self._conn.execute(
            "SELECT inventarnummer, kategorie_id, zustand FROM gegenstand "
            "WHERE inventarnummer = ?",
            (inventarnummer,),
        ).fetchone()
        if row is None:
            return None
        return Gegenstand(
            inventarnummer=row[0],
            kategorie_id=row[1],
            zustand=GegenstandZustand(row[2]),
        )
