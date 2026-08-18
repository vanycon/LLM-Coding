"""SQLite-Persistenz-Adapter für Kategorie."""
import sqlite3

from leihgut.domain.kategorie import Kategorie


class SqliteKategorieRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def find_by_id(self, kategorie_id: str) -> Kategorie | None:
        row = self._conn.execute(
            "SELECT kategorie_id, name, leihdauer_tage, wartungsintervall, "
            "einweisungspflichtig FROM kategorie WHERE kategorie_id = ?",
            (kategorie_id,),
        ).fetchone()
        if row is None:
            return None
        return self._to_domain(row)

    def insert(self, kategorie: Kategorie) -> None:
        self._conn.execute(
            "INSERT INTO kategorie "
            "(kategorie_id, name, leihdauer_tage, wartungsintervall, einweisungspflichtig) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                kategorie.kategorie_id,
                kategorie.name,
                kategorie.leihdauer_tage,
                kategorie.wartungsintervall,
                int(kategorie.einweisungspflichtig),
            ),
        )
        self._conn.commit()

    def update(self, kategorie: Kategorie) -> None:
        self._conn.execute(
            "UPDATE kategorie SET name = ?, leihdauer_tage = ?, "
            "wartungsintervall = ?, einweisungspflichtig = ? "
            "WHERE kategorie_id = ?",
            (
                kategorie.name,
                kategorie.leihdauer_tage,
                kategorie.wartungsintervall,
                int(kategorie.einweisungspflichtig),
                kategorie.kategorie_id,
            ),
        )
        self._conn.commit()

    @staticmethod
    def _to_domain(row) -> Kategorie:
        return Kategorie(
            kategorie_id=row[0],
            name=row[1],
            leihdauer_tage=row[2],
            wartungsintervall=row[3],
            einweisungspflichtig=bool(row[4]),
        )
