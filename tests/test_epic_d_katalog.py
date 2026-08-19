"""Tests für EPIC-D (Katalog pflegen, UC-09 / SI-09).

Umfasst: BR-KAT-01..06 (Kategorie & Gegenstand anlegen/ändern, Kaution).
"""
import sqlite3
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from leihgut.adapters.persistence.sqlite_gegenstand_repository import (
    SqliteGegenstandRepository,
    create_connection,
)
from leihgut.adapters.persistence.sqlite_kategorie_repository import (
    SqliteKategorieRepository,
)
from leihgut.anwendungskern.katalog_service import (
    GegenstandNichtGefunden,
    InventarnummerVergeben,
    KategorieNichtGefunden,
    WertUngueltig,
    _kategorie_werte_pruefen,
    _wiederbeschaffungswert_pruefen,
    kategorie_aendern,
    kategorie_anlegen,
    gegenstand_anlegen,
    gegenstand_wert_aendern,
)
from leihgut.domain.kaution import kaution_berechnen
from leihgut.adapters.rest.app import create_app
from tests.fakes import FakeClock


# --- Unit Tests: Operationen (reine Validierung) ---


class TestOperationen:
    """Test _kategorie_werte_pruefen und _wiederbeschaffungswert_pruefen."""

    def test_kategorie_werte_gueltig(self):
        """BR-KAT-02: Leihdauer > 0, Wartungsintervall > 0."""
        fehler = _kategorie_werte_pruefen(14, 90)
        assert fehler is None

    def test_kategorie_leihdauer_ungueltig(self):
        """BR-KAT-02: Leihdauer <= 0 abgelehnt."""
        fehler = _kategorie_werte_pruefen(0, 90)
        assert isinstance(fehler, WertUngueltig)
        assert fehler.feld == "leihdauerTage"
        assert fehler.wert == 0

    def test_kategorie_wartungsintervall_ungueltig(self):
        """BR-KAT-02: Wartungsintervall <= 0 abgelehnt."""
        fehler = _kategorie_werte_pruefen(14, -1)
        assert isinstance(fehler, WertUngueltig)
        assert fehler.feld == "wartungsintervall"

    def test_wiederbeschaffungswert_gueltig(self):
        """BR-KAT-03: Wert > 0 akzeptiert."""
        fehler = _wiederbeschaffungswert_pruefen(5000)
        assert fehler is None

    def test_wiederbeschaffungswert_ungueltig(self):
        """BR-KAT-03: Wert <= 0 abgelehnt."""
        fehler = _wiederbeschaffungswert_pruefen(0)
        assert isinstance(fehler, WertUngueltig)
        assert fehler.feld == "wiederbeschaffungswertCent"


# --- Property-Based Test: Kaution-Berechnung ---


class TestKautionBerechnung:
    """Property-based tests für kaution_berechnen() (BR-KAT-04)."""

    @given(wert_cent=st.integers(min_value=1, max_value=100000))
    @settings(max_examples=100)
    def test_kaution_ist_zwischen_500_und_10000_euro(self, wert_cent):
        """BR-KAT-04: Kaution liegt immer zwischen 5 und 100 Euro
        (500–10000 Cent), unabhängig vom Wiederbeschaffungswert."""
        kaution = kaution_berechnen(wert_cent)
        assert 500 <= kaution <= 10000

    @given(wert_cent=st.integers(min_value=1, max_value=100000))
    @settings(max_examples=100)
    def test_kaution_ist_ganzzahl_cent(self, wert_cent):
        """BR-KAT-04: Kaution ist immer ganzzahlig (in Cent) und ein
        Vielfaches von 100 (ganze Euro)."""
        kaution = kaution_berechnen(wert_cent)
        assert isinstance(kaution, int)
        assert kaution >= 0
        assert kaution % 100 == 0  # Vielfaches von 100

    def test_kaution_beispiele(self):
        """Spot-Check: Beispielwerte für BR-KAT-04 Rounding."""
        # 1€ → min 5€ (500 Cent)
        assert kaution_berechnen(100) >= 500
        # 500€ → max 100€ (10000 Cent)
        assert kaution_berechnen(1000000) <= 10000
        # Mid-range: 10€ Wert → ca. 2€ (20%), hochgerundet auf min 5€
        kaution = kaution_berechnen(1000)
        assert 500 <= kaution <= 10000


# --- Integration Tests: Service-Layer ---


@pytest.fixture
def conn():
    c = create_connection(":memory:")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture
def repos(conn):
    return {
        "kategorie": SqliteKategorieRepository(conn),
        "gegenstand": SqliteGegenstandRepository(conn),
    }


class TestKategorieService:
    """Integration tests für kategorie_anlegen, kategorie_aendern."""

    def test_kategorie_anlegen_erfolg(self, repos):
        """BR-KAT-02: Gültige Kategorie wird angelegt."""
        ergebnis = kategorie_anlegen(
            repos["kategorie"],
            "cat-1",
            "Werkzeug",
            14,
            90,
            False,
        )
        assert hasattr(ergebnis, "kategorie_id")
        assert ergebnis.kategorie_id == "cat-1"
        assert ergebnis.name == "Werkzeug"
        assert ergebnis.leihdauer_tage == 14

    def test_kategorie_anlegen_leihdauer_ungueltig(self, repos):
        """BR-KAT-02: Ungültige Leihdauer abgelehnt."""
        ergebnis = kategorie_anlegen(
            repos["kategorie"], "cat-1", "Werkzeug", 0, 90, False
        )
        assert isinstance(ergebnis, WertUngueltig)
        assert ergebnis.feld == "leihdauerTage"

    def test_kategorie_aendern_erfolg(self, repos):
        """Kategorie ändern: neue Leihdauer wird aktualisiert."""
        kategorie_anlegen(repos["kategorie"], "cat-1", "Werkzeug", 14, 90, False)

        ergebnis = kategorie_aendern(
            repos["kategorie"], "cat-1", 21, 60, False
        )
        assert ergebnis.leihdauer_tage == 21
        assert ergebnis.wartungsintervall == 60

    def test_kategorie_aendern_nicht_gefunden(self, repos):
        """Kategorie ändern auf nicht-existierende ID: 404."""
        ergebnis = kategorie_aendern(
            repos["kategorie"], "nonexistent", 14, 90, False
        )
        assert isinstance(ergebnis, KategorieNichtGefunden)


class TestGegenstandService:
    """Integration tests für gegenstand_anlegen, gegenstand_wert_aendern."""

    def test_gegenstand_anlegen_erfolg(self, repos):
        """BR-KAT-01/03: Gegenstand mit gültiger Kategorie wird angelegt."""
        kategorie_anlegen(repos["kategorie"], "cat-1", "Werkzeug", 14, 90, False)

        ergebnis = gegenstand_anlegen(
            repos["gegenstand"],
            repos["kategorie"],
            "inv-1",
            "cat-1",
            5000,
        )
        assert hasattr(ergebnis, "inventarnummer")
        assert ergebnis.inventarnummer == "inv-1"
        assert ergebnis.wiederbeschaffungswert_cent == 5000

    def test_gegenstand_anlegen_inventarnummer_vergeben(self, repos):
        """BR-KAT-01: Duplikat-Inventarnummer abgelehnt."""
        kategorie_anlegen(repos["kategorie"], "cat-1", "Werkzeug", 14, 90, False)
        gegenstand_anlegen(
            repos["gegenstand"],
            repos["kategorie"],
            "inv-1",
            "cat-1",
            5000,
        )

        # Zweiter Versuch mit gleicher Inventarnummer
        ergebnis = gegenstand_anlegen(
            repos["gegenstand"],
            repos["kategorie"],
            "inv-1",
            "cat-1",
            5000,
        )
        assert isinstance(ergebnis, InventarnummerVergeben)
        assert ergebnis.inventarnummer == "inv-1"

    def test_gegenstand_anlegen_kategorie_nicht_gefunden(self, repos):
        """Gegenstand mit nicht-existierender Kategorie: 404."""
        ergebnis = gegenstand_anlegen(
            repos["gegenstand"],
            repos["kategorie"],
            "inv-1",
            "nonexistent",
            5000,
        )
        assert isinstance(ergebnis, KategorieNichtGefunden)

    def test_gegenstand_anlegen_wert_ungueltig(self, repos):
        """BR-KAT-03: Ungültiger Wiederbeschaffungswert abgelehnt."""
        kategorie_anlegen(repos["kategorie"], "cat-1", "Werkzeug", 14, 90, False)

        ergebnis = gegenstand_anlegen(
            repos["gegenstand"],
            repos["kategorie"],
            "inv-1",
            "cat-1",
            0,  # ungültig
        )
        assert isinstance(ergebnis, WertUngueltig)

    def test_gegenstand_wert_aendern_erfolg(self, repos):
        """Gegenstand-Wert ändern: neuer Wert wird aktualisiert."""
        kategorie_anlegen(repos["kategorie"], "cat-1", "Werkzeug", 14, 90, False)
        gegenstand_anlegen(
            repos["gegenstand"],
            repos["kategorie"],
            "inv-1",
            "cat-1",
            5000,
        )

        ergebnis = gegenstand_wert_aendern(
            repos["gegenstand"], "inv-1", 7000
        )
        assert ergebnis.wiederbeschaffungswert_cent == 7000

    def test_gegenstand_wert_aendern_nicht_gefunden(self, repos):
        """Gegenstand-Wert ändern auf nicht-existierende ID: 404."""
        ergebnis = gegenstand_wert_aendern(
            repos["gegenstand"], "nonexistent", 5000
        )
        assert isinstance(ergebnis, GegenstandNichtGefunden)


# --- REST Tests ---


class TestRestKatalog:
    """REST-Tests für Katalog-Endpunkte."""

    @pytest.fixture
    def client(self, conn):
        app = create_app(conn, FakeClock(datetime(2026, 8, 19)))
        return TestClient(app)

    def test_post_kategorie_erfolg(self, client):
        """POST /kategorien mit Wart-Rolle: 201."""
        response = client.post(
            "/kategorien",
            json={
                "kategorieId": "cat-1",
                "name": "Werkzeug",
                "leihdauerTage": 14,
                "wartungsintervall": 90,
                "einweisungspflichtig": False,
            },
            headers={"X-Rolle": "wart"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["kategorieId"] == "cat-1"

    def test_post_kategorie_rolle_erforderlich(self, client):
        """Nur Wart darf Kategorien anlegen."""
        response = client.post(
            "/kategorien",
            json={
                "kategorieId": "cat-1",
                "name": "Werkzeug",
                "leihdauerTage": 14,
                "wartungsintervall": 90,
                "einweisungspflichtig": False,
            },
            headers={"X-Rolle": "mitglied"},
        )
        assert response.status_code == 403

    def test_put_kategorie_erfolg(self, client):
        """PUT /kategorien/{id} mit Wart-Rolle: 200."""
        # Erst anlegen
        client.post(
            "/kategorien",
            json={
                "kategorieId": "cat-1",
                "name": "Werkzeug",
                "leihdauerTage": 14,
                "wartungsintervall": 90,
                "einweisungspflichtig": False,
            },
            headers={"X-Rolle": "wart"},
        )

        # Dann ändern
        response = client.put(
            "/kategorien/cat-1",
            json={
                "leihdauerTage": 21,
                "wartungsintervall": 60,
                "einweisungspflichtig": False,
            },
            headers={"X-Rolle": "wart"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["leihdauerTage"] == 21

    def test_post_gegenstand_erfolg(self, client):
        """POST /gegenstaende mit Wart-Rolle und gültiger Kategorie: 201."""
        # Erst Kategorie anlegen
        client.post(
            "/kategorien",
            json={
                "kategorieId": "cat-1",
                "name": "Werkzeug",
                "leihdauerTage": 14,
                "wartungsintervall": 90,
                "einweisungspflichtig": False,
            },
            headers={"X-Rolle": "wart"},
        )

        # Dann Gegenstand
        response = client.post(
            "/gegenstaende",
            json={
                "inventarnummer": "inv-1",
                "kategorieId": "cat-1",
                "wiederbeschaffungswertCent": 5000,
            },
            headers={"X-Rolle": "wart"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["inventarnummer"] == "inv-1"

    def test_post_gegenstand_inventarnummer_vergeben(self, client):
        """POST /gegenstaende mit Duplikat-Inventarnummer: 409."""
        # Kategorie + Gegenstand anlegen
        client.post(
            "/kategorien",
            json={
                "kategorieId": "cat-1",
                "name": "Werkzeug",
                "leihdauerTage": 14,
                "wartungsintervall": 90,
                "einweisungspflichtig": False,
            },
            headers={"X-Rolle": "wart"},
        )
        client.post(
            "/gegenstaende",
            json={
                "inventarnummer": "inv-1",
                "kategorieId": "cat-1",
                "wiederbeschaffungswertCent": 5000,
            },
            headers={"X-Rolle": "wart"},
        )

        # Zweiter Versuch
        response = client.post(
            "/gegenstaende",
            json={
                "inventarnummer": "inv-1",
                "kategorieId": "cat-1",
                "wiederbeschaffungswertCent": 5000,
            },
            headers={"X-Rolle": "wart"},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["fehlercode"] == "INVENTARNUMMER_VERGEBEN"

    def test_put_gegenstand_erfolg(self, client):
        """PUT /gegenstaende/{inv} mit Wart-Rolle: 200."""
        # Setup
        client.post(
            "/kategorien",
            json={
                "kategorieId": "cat-1",
                "name": "Werkzeug",
                "leihdauerTage": 14,
                "wartungsintervall": 90,
                "einweisungspflichtig": False,
            },
            headers={"X-Rolle": "wart"},
        )
        client.post(
            "/gegenstaende",
            json={
                "inventarnummer": "inv-1",
                "kategorieId": "cat-1",
                "wiederbeschaffungswertCent": 5000,
            },
            headers={"X-Rolle": "wart"},
        )

        # Wert ändern
        response = client.put(
            "/gegenstaende/inv-1",
            json={"wiederbeschaffungswertCent": 7000},
            headers={"X-Rolle": "wart"},
        )
        assert response.status_code == 200
        assert response.json()["wiederbeschaffungswertCent"] == 7000

    def test_get_verfuegbarkeit_rolle_erforderlich(self, client):
        """GET /gegenstaende/verfuegbarkeit erlaubt Thekendienst/Mitglied/Wart."""
        response = client.get(
            "/gegenstaende/verfuegbarkeit?inventarnummer=inv-1",
            headers={"X-Rolle": "invalid"},
        )
        assert response.status_code == 403
