"""Skeleton-01 (Walking Skeleton): Verfügbarkeit eines Gegenstands abfragen.

Referenzen:
- src/docs/implementation/backlog.adoc, Abschnitt "Walking Skeleton"
- src/docs/specs/spec-use-cases.adoc, UC-10
- src/docs/specs/spec-system-interfaces.adoc, SI-10

Service-Level-Tests gegen eine echte SQLite-Datenbank (":memory:"), kein
Mocking von Repository oder Domänenmodell (TDD-Hamburg-Style /
Chicago-School-nah, siehe 08_concepts.adoc, Abschnitt Test).
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from leihgut.adapters.persistence.sqlite_gegenstand_repository import (
    SqliteGegenstandRepository,
    create_connection,
)
from leihgut.adapters.rest.app import create_app
from leihgut.anwendungskern.verfuegbarkeit_service import (
    GegenstandNichtGefunden,
    verfuegbarkeit_pruefen,
)


@pytest.fixture
def conn():
    connection = create_connection(":memory:")
    connection.execute(
        "INSERT INTO kategorie "
        "(kategorie_id, name, leihdauer_tage, wartungsintervall, einweisungspflichtig) "
        "VALUES (?, ?, ?, ?, ?)",
        ("kat-bohrmaschine", "Bohrmaschine", 14, 50, 0),
    )
    connection.execute(
        "INSERT INTO gegenstand "
        "(inventarnummer, kategorie_id, wiederbeschaffungswert_cent, nutzungszaehler, zustand) "
        "VALUES (?, ?, ?, ?, ?)",
        ("INV-001", "kat-bohrmaschine", 8000, 0, "verfuegbar"),
    )
    connection.commit()
    yield connection
    connection.close()


class TestVerfuegbarkeitPruefenService:
    """Service-Ebene: Anwendungsdienst gegen echtes Repository (UC-10)."""

    def test_uc10_liefert_zustand_fuer_vorhandenen_gegenstand(self, conn):
        repo = SqliteGegenstandRepository(conn)

        ergebnis = verfuegbarkeit_pruefen(repo, "INV-001")

        assert ergebnis.inventarnummer == "INV-001"
        assert ergebnis.kategorie_id == "kat-bohrmaschine"
        assert ergebnis.zustand.value == "verfuegbar"

    def test_uc10_lehnt_unbekannte_inventarnummer_ab(self, conn):
        repo = SqliteGegenstandRepository(conn)

        ergebnis = verfuegbarkeit_pruefen(repo, "UNBEKANNT")

        assert isinstance(ergebnis, GegenstandNichtGefunden)
        assert ergebnis.inventarnummer == "UNBEKANNT"


class TestVerfuegbarkeitPruefenRest:
    """Akzeptanz-Ebene: Ende-zu-Ende über die REST-API (SI-10)."""

    def test_si10_gibt_200_und_zustand_zurueck(self, conn):
        client = TestClient(create_app(conn))

        response = client.get(
            "/gegenstaende/INV-001", headers={"X-Rolle": "mitglied"}
        )

        assert response.status_code == 200
        assert response.json() == {
            "inventarnummer": "INV-001",
            "kategorieId": "kat-bohrmaschine",
            "zustand": "verfuegbar",
        }

    def test_si10_gibt_404_nicht_gefunden_zurueck(self, conn):
        client = TestClient(create_app(conn))

        response = client.get(
            "/gegenstaende/UNBEKANNT", headers={"X-Rolle": "mitglied"}
        )

        assert response.status_code == 404
        assert response.json()["detail"]["fehlercode"] == "NICHT_GEFUNDEN"


class TestAuditLogUnveraenderlichkeit:
    """ADR-009: Trigger verhindern nachträgliche UPDATE/DELETE-Operationen
    auf dem Audit-Log — Nachweis, dass der Mechanismus wirklich greift, nicht
    nur dokumentiert ist."""

    def _audit_eintrag_anlegen(self, conn):
        conn.execute(
            "INSERT INTO audit_log "
            "(zeitstempel, aggregat, aggregat_id, ereignisart, rolle) "
            "VALUES (?, ?, ?, ?, ?)",
            ("2026-08-18T10:00:00", "gegenstand", "INV-001", "angelegt", "wart"),
        )
        conn.commit()

    def test_update_wird_von_trigger_abgelehnt(self, conn):
        self._audit_eintrag_anlegen(conn)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE audit_log SET rolle = 'thekendienst'")

    def test_delete_wird_von_trigger_abgelehnt(self, conn):
        self._audit_eintrag_anlegen(conn)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM audit_log")


class TestNebenlaeufigkeitAktiveAusleihe:
    """ADR-007: partieller Unique-Index verhindert zwei gleichzeitig aktive
    Ausleihen desselben Gegenstands auf DB-Ebene (Vorstufe für EPIC-A; hier
    wird nur der Datenbank-Constraint selbst geprüft, nicht der
    Anwendungsdienst, der in EPIC-A entsteht)."""

    def test_zweite_aktive_ausleihe_fuer_denselben_gegenstand_schlaegt_fehl(
        self, conn
    ):
        conn.execute(
            "INSERT INTO ausleihe "
            "(ausleihe_id, gegenstand_id, mitglied_id, ausgabedatum, "
            "rueckgabefrist, kaution_cent, verlaengert, zustand) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("A-1", "INV-001", "M-1", "2026-08-18", "2026-09-01", 1600, 0, "aktiv"),
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ausleihe "
                "(ausleihe_id, gegenstand_id, mitglied_id, ausgabedatum, "
                "rueckgabefrist, kaution_cent, verlaengert, zustand) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("A-2", "INV-001", "M-2", "2026-08-18", "2026-09-01", 1600, 0, "aktiv"),
            )
