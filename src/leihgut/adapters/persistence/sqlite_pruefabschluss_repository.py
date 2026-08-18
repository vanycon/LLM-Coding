"""SQLite-Persistenz-Adapter für den atomaren Prüfabschluss (UC-04).

Bündelt alle Schreibvorgänge aus UC-04 in einer einzigen Transaktion
(`BEGIN IMMEDIATE` … `COMMIT`), wie es das Backlog
(`epic-b-pruefung-kaution.adoc`) für diese Story explizit verlangt.
"""
import sqlite3

from leihgut.domain.audit_log import AuditLogEintrag
from leihgut.domain.ausleihe import Ausleihe
from leihgut.domain.gegenstand import Gegenstand
from leihgut.domain.kautionsbewegung import Kautionsbewegung
from leihgut.domain.maengel import MaengelEintrag
from leihgut.domain.pruefprotokoll import Pruefprotokoll


class SqlitePruefabschlussRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def abschliessen(
        self,
        ausleihe: Ausleihe,
        gegenstand: Gegenstand,
        pruefprotokoll: Pruefprotokoll,
        neue_maengel: list[MaengelEintrag],
        kautionsbewegungen: list[Kautionsbewegung],
        audit_eintrag: AuditLogEintrag,
    ) -> None:
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE ausleihe SET zustand = ? WHERE ausleihe_id = ?",
                (ausleihe.zustand.value, ausleihe.ausleihe_id),
            )
            conn.execute(
                "UPDATE gegenstand SET zustand = ?, nutzungszaehler = ? "
                "WHERE inventarnummer = ?",
                (
                    gegenstand.zustand.value,
                    gegenstand.nutzungszaehler,
                    gegenstand.inventarnummer,
                ),
            )
            conn.execute(
                "INSERT INTO pruefprotokoll "
                "(pruefprotokoll_id, ausleihe_id, kautionsabzug_cent, "
                "zielzustand, erstellt_am) VALUES (?, ?, ?, ?, ?)",
                (
                    pruefprotokoll.pruefprotokoll_id,
                    pruefprotokoll.ausleihe_id,
                    pruefprotokoll.kautionsabzug_cent,
                    pruefprotokoll.zielzustand,
                    pruefprotokoll.erstellt_am,
                ),
            )
            for mangel in neue_maengel:
                conn.execute(
                    "INSERT INTO maengel_eintrag "
                    "(maengel_id, gegenstand_id, beschreibung, "
                    "festgestellt_in_pruefprotokoll_id) VALUES (?, ?, ?, ?)",
                    (
                        mangel.maengel_id,
                        mangel.gegenstand_id,
                        mangel.beschreibung,
                        mangel.festgestellt_in_pruefprotokoll_id,
                    ),
                )
            for bewegung in kautionsbewegungen:
                conn.execute(
                    "INSERT INTO kautionsbewegung "
                    "(bewegung_id, ausleihe_id, art, betrag_cent, "
                    "zeitstempel, ausloeser) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        bewegung.bewegung_id,
                        bewegung.ausleihe_id,
                        bewegung.art.value,
                        bewegung.betrag_cent,
                        bewegung.zeitstempel,
                        bewegung.ausloeser,
                    ),
                )
            conn.execute(
                "INSERT INTO audit_log "
                "(zeitstempel, aggregat, aggregat_id, ereignisart, rolle, "
                "werte_vorher, werte_nachher) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    audit_eintrag.zeitstempel,
                    audit_eintrag.aggregat,
                    audit_eintrag.aggregat_id,
                    audit_eintrag.ereignisart,
                    audit_eintrag.rolle,
                    audit_eintrag.werte_vorher,
                    audit_eintrag.werte_nachher,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
