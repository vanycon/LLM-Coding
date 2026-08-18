"""SQLite-Persistenz-Adapter für die Mängelliste (BR-RUP-05)."""
import sqlite3

from leihgut.domain.maengel import MaengelEintrag


class SqliteMaengelRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def find_by_gegenstand(self, gegenstand_id: str) -> list[MaengelEintrag]:
        rows = self._conn.execute(
            "SELECT maengel_id, gegenstand_id, beschreibung, "
            "festgestellt_in_pruefprotokoll_id FROM maengel_eintrag "
            "WHERE gegenstand_id = ?",
            (gegenstand_id,),
        ).fetchall()
        return [
            MaengelEintrag(
                maengel_id=row[0],
                gegenstand_id=row[1],
                beschreibung=row[2],
                festgestellt_in_pruefprotokoll_id=row[3],
            )
            for row in rows
        ]
