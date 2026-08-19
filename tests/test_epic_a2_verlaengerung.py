"""Tests für EPIC-A2 (Ausleihe verlängern, UC-02 / SI-02).

Umfasst: BR-AUS-06 (1x Verlängerung), BR-AUS-07 (nicht überfällig, keine Vormerkung),
BR-AUS-08 (Mitglied nicht gesperrt), BR-AUS-09 (Kaution unverändert).
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from leihgut.adapters.persistence.sqlite_ausleihe_repository import (
    SqliteAusleiheRepository,
)
from leihgut.adapters.persistence.sqlite_gegenstand_repository import (
    SqliteGegenstandRepository,
    create_connection,
)
from leihgut.adapters.persistence.sqlite_kategorie_repository import (
    SqliteKategorieRepository,
)
from leihgut.adapters.rest.app import create_app
from leihgut.anwendungskern.verlaengerung_service import (
    AusleiheNichtGefunden,
    AusleiheUeberfaellig,
    BereitsVerlaengert,
    MitgliedGesperrt,
    ausleihe_verlaengern,
)
from leihgut.domain.ausleihe import AusleiheZustand
from tests.fakes import FakeClock
from datetime import datetime


def create_connection_with_data():
    """Test-DB mit Kategorie, Gegenstand, aktiver Ausleihe."""
    conn = create_connection(":memory:")
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        INSERT INTO kategorie (kategorie_id, name, leihdauer_tage,
                              wartungsintervall, einweisungspflichtig)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("cat-1", "Werkzeug", 14, 20, False),
    )

    conn.execute(
        """
        INSERT INTO gegenstand (inventarnummer, kategorie_id, zustand,
                               wiederbeschaffungswert_cent, nutzungszaehler)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("inv-1", "cat-1", "verfuegbar", 5000, 0),
    )

    conn.execute(
        """
        INSERT INTO ausleihe (ausleihe_id, gegenstand_id, mitglied_id,
                             ausgabedatum, rueckgabefrist, kaution_cent,
                             verlaengert, zustand, rueckgabe_auffaelligkeiten)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "lease-1",
            "inv-1",
            "member-1",
            "2026-08-01",
            "2026-08-29",  # noch 10 Tage (verlaengert wird um 14 -> 2026-09-12)
            2000,
            0,  # verlaengert: False
            "aktiv",
            None,
        ),
    )

    conn.commit()
    return conn


@pytest.fixture
def conn():
    c = create_connection_with_data()
    yield c
    c.close()


@pytest.fixture
def repos(conn):
    return {
        "gegenstand": SqliteGegenstandRepository(conn),
        "kategorie": SqliteKategorieRepository(conn),
        "ausleihe": SqliteAusleiheRepository(conn),
    }


@pytest.fixture
def clock():
    return FakeClock(datetime(2026, 8, 19, 10, 0, 0))


class TestVerlaengerungService:
    """Integration tests für `ausleihe_verlaengern` Service."""

    def test_erfolgreiche_verlaengerung_direkter_repo_zugriff(self):
        """Happy Path: Ausleihe verlängert, Frist um 14 Tage verschoben."""
        conn = create_connection_with_data()
        repo_ausleihe = SqliteAusleiheRepository(conn)
        repo_kategorie = SqliteKategorieRepository(conn)
        repo_gegenstand = SqliteGegenstandRepository(conn)
        clock = FakeClock(datetime(2026, 8, 19, 10, 0, 0))

        ergebnis = ausleihe_verlaengern(
            repo_ausleihe, repo_kategorie, repo_gegenstand, clock, "lease-1"
        )

        assert not isinstance(ergebnis, (AusleiheNichtGefunden, AusleiheUeberfaellig, BereitsVerlaengert, MitgliedGesperrt))
        assert ergebnis.rueckgabefrist == "2026-09-12"  # 2026-08-29 + 14 Tage
        assert ergebnis.verlaengert is True
        assert ergebnis.kaution_cent == 2000  # BR-AUS-09: unverändert
        assert ergebnis.zustand == AusleiheZustand.AKTIV
        conn.close()

    def test_ausleihe_nicht_gefunden_direkter_repo_zugriff(self):
        """Ausleihe existiert nicht: 404."""
        conn = create_connection_with_data()
        repo_ausleihe = SqliteAusleiheRepository(conn)
        repo_kategorie = SqliteKategorieRepository(conn)
        repo_gegenstand = SqliteGegenstandRepository(conn)
        clock = FakeClock(datetime(2026, 8, 19, 10, 0, 0))

        ergebnis = ausleihe_verlaengern(
            repo_ausleihe, repo_kategorie, repo_gegenstand, clock, "nonexistent"
        )
        assert isinstance(ergebnis, AusleiheNichtGefunden)
        conn.close()

    def test_ausleihe_ueberfaellig_direkter_repo_zugriff(self):
        """Ausleihe überfällig (Frist < heute): 409."""
        conn = create_connection_with_data()
        conn.execute(
            "UPDATE ausleihe SET rueckgabefrist = ? WHERE ausleihe_id = ?",
            ("2026-08-18", "lease-1"),  # heute ist 2026-08-19
        )
        conn.commit()

        repo_ausleihe = SqliteAusleiheRepository(conn)
        repo_kategorie = SqliteKategorieRepository(conn)
        repo_gegenstand = SqliteGegenstandRepository(conn)
        clock = FakeClock(datetime(2026, 8, 19, 10, 0, 0))

        ergebnis = ausleihe_verlaengern(
            repo_ausleihe, repo_kategorie, repo_gegenstand, clock, "lease-1"
        )
        assert isinstance(ergebnis, AusleiheUeberfaellig)
        conn.close()

    def test_mitglied_gesperrt_direkter_repo_zugriff(self):
        """Mitglied ist gesperrt: 409."""
        conn = create_connection_with_data()
        conn.execute(
            "UPDATE ausleihe SET mitglied_gesperrt = ? WHERE ausleihe_id = ?",
            (True, "lease-1"),
        )
        conn.commit()

        repo_ausleihe = SqliteAusleiheRepository(conn)
        repo_kategorie = SqliteKategorieRepository(conn)
        repo_gegenstand = SqliteGegenstandRepository(conn)
        clock = FakeClock(datetime(2026, 8, 19, 10, 0, 0))

        ergebnis = ausleihe_verlaengern(
            repo_ausleihe, repo_kategorie, repo_gegenstand, clock, "lease-1"
        )
        assert isinstance(ergebnis, MitgliedGesperrt)
        conn.close()

    def test_bereits_verlaengert_direkter_repo_zugriff(self):
        """Ausleihe wurde schon verlängert (BR-AUS-06): 409."""
        conn = create_connection_with_data()
        conn.execute(
            "UPDATE ausleihe SET verlaengert = ? WHERE ausleihe_id = ?",
            (True, "lease-1"),
        )
        conn.commit()

        repo_ausleihe = SqliteAusleiheRepository(conn)
        repo_kategorie = SqliteKategorieRepository(conn)
        repo_gegenstand = SqliteGegenstandRepository(conn)
        clock = FakeClock(datetime(2026, 8, 19, 10, 0, 0))

        ergebnis = ausleihe_verlaengern(
            repo_ausleihe, repo_kategorie, repo_gegenstand, clock, "lease-1"
        )
        assert isinstance(ergebnis, BereitsVerlaengert)
        conn.close()


class TestRestVerlaengerung:
    """REST-Tests für POST /ausleihen/{ausleiheId}/verlaengerung."""

    @pytest.fixture
    def client(self, conn, clock):
        app = create_app(conn, clock)
        return TestClient(app)

    def test_verlaengerung_erfolg(self, client):
        """POST /ausleihen/lease-1/verlaengerung mit Thekendienst-Rolle: 200."""
        response = client.post(
            "/ausleihen/lease-1/verlaengerung",
            headers={"X-Rolle": "thekendienst"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ausleiheId"] == "lease-1"
        assert data["rueckgabefrist"] == "2026-09-12"  # 2026-08-29 + 14 Tage
        assert data["verlaengert"] is True

    def test_verlaengerung_ausleihe_nicht_gefunden(self, client):
        """POST nonexistent ausleiheId: 404."""
        response = client.post(
            "/ausleihen/nonexistent/verlaengerung",
            headers={"X-Rolle": "thekendienst"},
        )

        assert response.status_code == 404
        assert response.json()["detail"]["fehlercode"] == "AUSLEIHE_NICHT_GEFUNDEN"

    def test_verlaengerung_ueberfaellig(self, conn, client):
        """Ausleihe überfällig: 409."""
        conn.execute(
            "UPDATE ausleihe SET rueckgabefrist = ? WHERE ausleihe_id = ?",
            ("2026-08-15", "lease-1"),
        )
        conn.commit()

        response = client.post(
            "/ausleihen/lease-1/verlaengerung",
            headers={"X-Rolle": "thekendienst"},
        )

        assert response.status_code == 409
        assert response.json()["detail"]["fehlercode"] == "AUSLEIHE_UEBERFAELLIG"

    def test_verlaengerung_mitglied_gesperrt(self, conn, client):
        """Mitglied gesperrt: 409."""
        conn.execute(
            "UPDATE ausleihe SET mitglied_gesperrt = ? WHERE ausleihe_id = ?",
            (True, "lease-1"),
        )
        conn.commit()

        response = client.post(
            "/ausleihen/lease-1/verlaengerung",
            headers={"X-Rolle": "thekendienst"},
        )

        assert response.status_code == 409
        assert response.json()["detail"]["fehlercode"] == "MITGLIED_GESPERRT"

    def test_verlaengerung_bereits_verlaengert(self, conn, client):
        """Bereits verlängert: 409."""
        conn.execute(
            "UPDATE ausleihe SET verlaengert = ? WHERE ausleihe_id = ?",
            (True, "lease-1"),
        )
        conn.commit()

        response = client.post(
            "/ausleihen/lease-1/verlaengerung",
            headers={"X-Rolle": "thekendienst"},
        )

        assert response.status_code == 409
        assert response.json()["detail"]["fehlercode"] == "BEREITS_VERLAENGERT"

    def test_verlaengerung_rolle_erforderlich(self, client):
        """Nur Thekendienst darf verlängern."""
        response = client.post(
            "/ausleihen/lease-1/verlaengerung",
            headers={"X-Rolle": "wart"},
        )

        assert response.status_code == 403
