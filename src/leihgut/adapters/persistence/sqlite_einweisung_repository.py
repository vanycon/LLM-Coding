"""SQLite-Persistenz-Adapter für Einweisung."""
import sqlite3

from leihgut.domain.einweisung import Einweisung


class SqliteEinweisungRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def find_by_id(self, einweisung_id: str) -> Einweisung | None:
        row = self._conn.execute(
            "SELECT einweisung_id, mitglied_id, kategorie_id, erstellt_am, "
            "widerrufen_am FROM einweisung WHERE einweisung_id = ?",
            (einweisung_id,),
        ).fetchone()
        if row is None:
            return None
        return self._to_domain(row)

    def find_gueltige(
        self, mitglied_id: str, kategorie_id: str
    ) -> Einweisung | None:
        row = self._conn.execute(
            "SELECT einweisung_id, mitglied_id, kategorie_id, erstellt_am, "
            "widerrufen_am FROM einweisung "
            "WHERE mitglied_id = ? AND kategorie_id = ? AND widerrufen_am IS NULL",
            (mitglied_id, kategorie_id),
        ).fetchone()
        if row is None:
            return None
        return self._to_domain(row)

    def insert(self, einweisung: Einweisung) -> None:
        self._conn.execute(
            "INSERT INTO einweisung "
            "(einweisung_id, mitglied_id, kategorie_id, erstellt_am, widerrufen_am) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                einweisung.einweisung_id,
                einweisung.mitglied_id,
                einweisung.kategorie_id,
                einweisung.erstellt_am,
                einweisung.widerrufen_am,
            ),
        )
        self._conn.commit()

    def widerrufen(self, einweisung_id: str, widerrufen_am: str) -> None:
        self._conn.execute(
            "UPDATE einweisung SET widerrufen_am = ? WHERE einweisung_id = ?",
            (widerrufen_am, einweisung_id),
        )
        self._conn.commit()

    @staticmethod
    def _to_domain(row) -> Einweisung:
        return Einweisung(
            einweisung_id=row[0],
            mitglied_id=row[1],
            kategorie_id=row[2],
            erstellt_am=row[3],
            widerrufen_am=row[4],
        )
