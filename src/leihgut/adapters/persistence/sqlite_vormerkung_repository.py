"""SQLite-Persistenz-Adapter für Vormerkung."""
import sqlite3
import uuid

from leihgut.domain.vormerkung import Vormerkung, VormerkungStatus


class SqliteVormerkungRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def find_by_id(self, vormerkung_id: str) -> Vormerkung | None:
        row = self._conn.execute(
            "SELECT vormerkung_id, kategorie_id, mitglied_id, erstellt_am, "
            "status, reihenfolge FROM vormerkung WHERE vormerkung_id = ?",
            (vormerkung_id,),
        ).fetchone()
        if row is None:
            return None
        return self._to_domain(row)

    def find_offene_je_mitglied_kategorie(
        self, mitglied_id: str, kategorie_id: str
    ) -> Vormerkung | None:
        row = self._conn.execute(
            "SELECT vormerkung_id, kategorie_id, mitglied_id, erstellt_am, "
            "status, reihenfolge FROM vormerkung "
            "WHERE mitglied_id = ? AND kategorie_id = ? AND status = ?",
            (mitglied_id, kategorie_id, VormerkungStatus.OFFEN.value),
        ).fetchone()
        if row is None:
            return None
        return self._to_domain(row)

    def find_offene_je_kategorie_sortiert_nach_reihenfolge(
        self, kategorie_id: str
    ) -> list[Vormerkung]:
        rows = self._conn.execute(
            "SELECT vormerkung_id, kategorie_id, mitglied_id, erstellt_am, "
            "status, reihenfolge FROM vormerkung "
            "WHERE kategorie_id = ? AND status = ? "
            "ORDER BY reihenfolge ASC",
            (kategorie_id, VormerkungStatus.OFFEN.value),
        ).fetchall()
        return [self._to_domain(row) for row in rows]

    def insert(self, vormerkung: Vormerkung) -> None:
        # Wenn ID leer, generiere UUID
        vormerkung_id = vormerkung.vormerkung_id or str(uuid.uuid4())
        
        self._conn.execute(
            "INSERT INTO vormerkung "
            "(vormerkung_id, kategorie_id, mitglied_id, erstellt_am, status, reihenfolge) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                vormerkung_id,
                vormerkung.kategorie_id,
                vormerkung.mitglied_id,
                vormerkung.erstellt_am,
                vormerkung.status.value,
                vormerkung.reihenfolge,
            ),
        )
        self._conn.commit()

    def update(self, vormerkung: Vormerkung) -> None:
        self._conn.execute(
            "UPDATE vormerkung SET status = ?, reihenfolge = ? WHERE vormerkung_id = ?",
            (vormerkung.status.value, vormerkung.reihenfolge, vormerkung.vormerkung_id),
        )
        self._conn.commit()

    @staticmethod
    def _to_domain(row) -> Vormerkung:
        return Vormerkung(
            vormerkung_id=row[0],
            kategorie_id=row[1],
            mitglied_id=row[2],
            erstellt_am=row[3],
            status=VormerkungStatus(row[4]),
            reihenfolge=row[5],
        )
