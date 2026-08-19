"""SQLite Persistence Adapter für Vormerkung Aggregate."""
import sqlite3
import uuid

from leihgut.domain.vormerkung import Vormerkung
from leihgut.ports.vormerkung_repository import VormerkungRepository


class SqliteVormerkungRepository(VormerkungRepository):
    """SQLite-Implementierung des Vormerkung Repository."""

    _SELECT_SPALTEN = (
        "vormerkung_id, kategorie_id, mitglied_id, status, reihenfolge, erstellt_am"
    )

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def find_by_id(self, vormerkung_id: str) -> Vormerkung | None:
        """Finde Vormerkung nach ID (egal ob offen oder abgesagt)."""
        cursor = self._conn.execute(
            f"SELECT {self._SELECT_SPALTEN} FROM vormerkung WHERE vormerkung_id = ?",
            (vormerkung_id,),
        )
        row = cursor.fetchone()
        return self._to_domain(row) if row else None

    def find_offene_je_mitglied_kategorie(self, mitglied_id: str, kategorie_id: str) -> Vormerkung | None:
        """Finde offene Vormerkung für (Mitglied, Kategorie) oder None."""
        cursor = self._conn.execute(
            f"SELECT {self._SELECT_SPALTEN} FROM vormerkung "
            "WHERE mitglied_id = ? AND kategorie_id = ? AND status = 'offen'",
            (mitglied_id, kategorie_id),
        )
        row = cursor.fetchone()
        return self._to_domain(row) if row else None

    def find_erste_offene_je_kategorie(self, kategorie_id: str) -> Vormerkung | None:
        """Finde erste (reihenfolge=1) offene Vormerkung für Kategorie, oder None."""
        cursor = self._conn.execute(
            f"SELECT {self._SELECT_SPALTEN} FROM vormerkung "
            "WHERE kategorie_id = ? AND status = 'offen' "
            "ORDER BY reihenfolge ASC LIMIT 1",
            (kategorie_id,),
        )
        row = cursor.fetchone()
        return self._to_domain(row) if row else None

    def count_offene_je_kategorie(self, kategorie_id: str) -> int:
        """Zähle offene Vormerkungen für Kategorie."""
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM vormerkung WHERE kategorie_id = ? AND status = 'offen'",
            (kategorie_id,),
        )
        return cursor.fetchone()[0]

    def insert(self, vormerkung: Vormerkung) -> None:
        """Füge neue Vormerkung ein."""
        # Wenn einweisungId leer, generiere UUID
        vormerkung_id = vormerkung.vormerkung_id or str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO vormerkung "
            "(vormerkung_id, kategorie_id, mitglied_id, status, reihenfolge, erstellt_am) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                vormerkung_id,
                vormerkung.kategorie_id,
                vormerkung.mitglied_id,
                vormerkung.status,
                vormerkung.reihenfolge,
                vormerkung.erstellt_am,
            ),
        )
        self._conn.commit()

    def update(self, vormerkung: Vormerkung) -> None:
        """Update bestehende Vormerkung (z.B. Status ändern)."""
        self._conn.execute(
            "UPDATE vormerkung SET status = ?, reihenfolge = ? WHERE vormerkung_id = ?",
            (vormerkung.status, vormerkung.reihenfolge, vormerkung.vormerkung_id),
        )
        self._conn.commit()

    @staticmethod
    def _to_domain(row: tuple) -> Vormerkung:
        """Mapper: DB-Row → Domain Vormerkung."""
        return Vormerkung(
            vormerkung_id=row[0],
            kategorie_id=row[1],
            mitglied_id=row[2],
            status=row[3],
            reihenfolge=row[4],
            erstellt_am=row[5],
        )
