"""SQLite-Persistenz-Adapter für Ausleihe."""
import sqlite3

from leihgut.domain.ausleihe import Ausleihe, AusleiheZustand
from leihgut.ports.ausleihe_repository import NebenlaeufigeAusgabeAbgelehnt

_SELECT_SPALTEN = (
    "ausleihe_id, gegenstand_id, mitglied_id, ausgabedatum, rueckgabefrist, "
    "kaution_cent, verlaengert, zustand, rueckgabe_auffaelligkeiten"
)


class SqliteAusleiheRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def find_by_id(self, ausleihe_id: str) -> Ausleihe | None:
        row = self._conn.execute(
            f"SELECT {_SELECT_SPALTEN} FROM ausleihe WHERE ausleihe_id = ?",
            (ausleihe_id,),
        ).fetchone()
        if row is None:
            return None
        return self._to_domain(row)

    def finde_offene_fuer_mitglied(self, mitglied_id: str) -> list[Ausleihe]:
        rows = self._conn.execute(
            f"SELECT {_SELECT_SPALTEN} FROM ausleihe "
            "WHERE mitglied_id = ? AND zustand IN ('aktiv', 'zurueckgegeben')",
            (mitglied_id,),
        ).fetchall()
        return [self._to_domain(row) for row in rows]

    def insert(self, ausleihe: Ausleihe) -> None:
        """ADR-007: `BEGIN IMMEDIATE` nimmt die Schreibsperre vor dem
        eigentlichen Schreiben; der partielle Unique-Index
        `ux_ausleihe_aktiv_je_gegenstand` ist die zweite, DB-erzwungene
        Schranke gegen zwei aktive Ausleihen desselben Gegenstands."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                "INSERT INTO ausleihe "
                "(ausleihe_id, gegenstand_id, mitglied_id, ausgabedatum, "
                "rueckgabefrist, kaution_cent, verlaengert, zustand) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ausleihe.ausleihe_id,
                    ausleihe.gegenstand_id,
                    ausleihe.mitglied_id,
                    ausleihe.ausgabedatum,
                    ausleihe.rueckgabefrist,
                    ausleihe.kaution_cent,
                    int(ausleihe.verlaengert),
                    ausleihe.zustand.value,
                ),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            self._conn.rollback()
            raise NebenlaeufigeAusgabeAbgelehnt(ausleihe.gegenstand_id) from exc

    def update(self, ausleihe: Ausleihe) -> None:
        self._conn.execute(
            "UPDATE ausleihe SET rueckgabefrist = ?, kaution_cent = ?, "
            "verlaengert = ?, zustand = ?, rueckgabe_auffaelligkeiten = ? "
            "WHERE ausleihe_id = ?",
            (
                ausleihe.rueckgabefrist,
                ausleihe.kaution_cent,
                int(ausleihe.verlaengert),
                ausleihe.zustand.value,
                ausleihe.rueckgabe_auffaelligkeiten,
                ausleihe.ausleihe_id,
            ),
        )
        self._conn.commit()

    @staticmethod
    def _to_domain(row) -> Ausleihe:
        return Ausleihe(
            ausleihe_id=row[0],
            gegenstand_id=row[1],
            mitglied_id=row[2],
            ausgabedatum=row[3],
            rueckgabefrist=row[4],
            kaution_cent=row[5],
            verlaengert=bool(row[6]),
            zustand=AusleiheZustand(row[7]),
            rueckgabe_auffaelligkeiten=row[8],
        )
