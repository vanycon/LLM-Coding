"""Test-Suite für UC-06 (Verlust melden) / SI-06.

Service-Layer-Tests (Hamburg-Style: Service-Boundary mit minimal mocking)
+ REST-Layer-Tests (Rollenschutz, HTTP-Contract)
"""
import pytest

from leihgut.adapters.persistence.sqlite_ausleihe_repository import (
    SqliteAusleiheRepository,
)
from leihgut.adapters.persistence.sqlite_einweisung_repository import (
    SqliteEinweisungRepository,
)
from leihgut.adapters.persistence.sqlite_gegenstand_repository import (
    SqliteGegenstandRepository,
    create_connection,
)
from leihgut.adapters.persistence.sqlite_kategorie_repository import (
    SqliteKategorieRepository,
)
from leihgut.adapters.persistence.sqlite_audit_log_repository import (
    SqliteAuditLogRepository,
)
from leihgut.adapters.rest.app import create_app
from leihgut.anwendungskern.ausleihe_service import gegenstand_ausgeben
from leihgut.anwendungskern.verlust_service import (
    AusleiheNichtAktiv,
    AusleiheNichtGefunden,
    verlust_erfassen,
)
from leihgut.domain.ausleihe import AusleiheZustand
from leihgut.domain.gegenstand import GegenstandZustand
from starlette.testclient import TestClient
from tests.fakes import FakeClock


@pytest.fixture
def conn():
    """In-Memory SQLite für Tests."""
    connection = create_connection(":memory:")
    # Setup: Kategorien
    connection.execute(
        "INSERT INTO kategorie "
        "(kategorie_id, name, leihdauer_tage, wartungsintervall, einweisungspflichtig) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Cat1", "Kategorie 1", 14, 20, 0),
    )
    connection.execute(
        "INSERT INTO kategorie "
        "(kategorie_id, name, leihdauer_tage, wartungsintervall, einweisungspflichtig) "
        "VALUES (?, ?, ?, ?, ?)",
        ("Werkzeug", "Werkzeug-Kategorie", 14, 20, 0),
    )
    connection.commit()
    yield connection
    connection.close()


def _gegenstand_anlegen(conn, inventarnummer, kategorie_id, wbw, zustand="verfuegbar"):
    """Hilfsfunktion: Gegenstand in DB anlegen."""
    conn.execute(
        "INSERT INTO gegenstand "
        "(inventarnummer, kategorie_id, wiederbeschaffungswert_cent, "
        "nutzungszaehler, zustand) VALUES (?, ?, ?, 0, ?)",
        (inventarnummer, kategorie_id, wbw, zustand),
    )
    conn.commit()


@pytest.fixture
def ausleihe_repo(conn):
    return SqliteAusleiheRepository(conn)


@pytest.fixture
def gegenstand_repo(conn):
    return SqliteGegenstandRepository(conn)


@pytest.fixture
def kategorie_repo(conn):
    return SqliteKategorieRepository(conn)


@pytest.fixture
def einweisung_repo(conn):
    return SqliteEinweisungRepository(conn)


@pytest.fixture
def vormerkung_repo(conn):
    from leihgut.adapters.persistence.sqlite_vormerkung_repository import (
        SqliteVormerkungRepository,
    )
    return SqliteVormerkungRepository(conn)


@pytest.fixture
def clock():
    return FakeClock("2026-08-19T12:00:00Z")


@pytest.fixture
def audit_log_repo(conn):
    return SqliteAuditLogRepository(conn)


class TestVerlustServiceValidierung:
    """UC-06: Validierungslogik (Isolation)."""

    def test_ausleihe_nicht_gefunden(self, conn, ausleihe_repo, gegenstand_repo, audit_log_repo, clock):
        """Validierung: Ausleihe existiert nicht → 404."""
        ergebnis = verlust_erfassen(
            conn, ausleihe_repo, gegenstand_repo, audit_log_repo, clock, "nichtexistent", "wart"
        )
        assert isinstance(ergebnis, AusleiheNichtGefunden)
        assert ergebnis.ausleihe_id == "nichtexistent"

    def test_ausleihe_nicht_aktiv_zurueckgegeben(
        self, conn, ausleihe_repo, gegenstand_repo, kategorie_repo, einweisung_repo, audit_log_repo, clock, vormerkung_repo
    ):
        """BR-VER-02: Nur aktive Ausleihen können verloren sein (zurueckgegeben) → 409."""
        # Setup: Gegenstand
        _gegenstand_anlegen(conn, "inv-1", "Cat1", 10000)

        # Setup: Ausleihe ausgeben
        ausleihe_1 = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo, vormerkung_repo, audit_log_repo, clock, "inv-1", "m1"
        )
        assert isinstance(ausleihe_1, Exception) is False  # Should be Ausleihe

        # Simuliere: zurueckgegeben setzen
        conn.execute(
            "UPDATE ausleihe SET zustand = ? WHERE ausleihe_id = ?",
            (AusleiheZustand.ZURUECKGEGEBEN.value, ausleihe_1.ausleihe_id),
        )
        conn.commit()

        # Test: Verlust auf zurueckgegeben → 409
        ergebnis = verlust_erfassen(
            conn, ausleihe_repo, gegenstand_repo, audit_log_repo, clock, ausleihe_1.ausleihe_id, "wart"
        )
        assert isinstance(ergebnis, AusleiheNichtAktiv)
        assert ergebnis.aktueller_zustand == "zurueckgegeben"

    def test_ausleihe_nicht_aktiv_abgeschlossen(
        self, conn, ausleihe_repo, gegenstand_repo, kategorie_repo, einweisung_repo, audit_log_repo, clock, vormerkung_repo
    ):
        """BR-VER-02: Nur aktive Ausleihen können verloren sein (abgeschlossen) → 409."""
        # Setup: Gegenstand
        _gegenstand_anlegen(conn, "inv-1", "Cat1", 10000)

        # Setup: Ausleihe ausgeben
        ausleihe_1 = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo, vormerkung_repo, audit_log_repo, clock, "inv-1", "m1"
        )

        # Simuliere: abgeschlossen setzen
        conn.execute(
            "UPDATE ausleihe SET zustand = ? WHERE ausleihe_id = ?",
            (AusleiheZustand.ABGESCHLOSSEN.value, ausleihe_1.ausleihe_id),
        )
        conn.commit()

        # Test: Verlust auf abgeschlossen → 409
        ergebnis = verlust_erfassen(
            conn, ausleihe_repo, gegenstand_repo, audit_log_repo, clock, ausleihe_1.ausleihe_id, "wart"
        )
        assert isinstance(ergebnis, AusleiheNichtAktiv)
        assert ergebnis.aktueller_zustand == "abgeschlossen"


class TestVerlustServiceHappyPath:
    """UC-06: Happy Path (alle Zustandsübergänge)."""

    def test_verlust_erfassen_ausleihe_zustand_uebergang(
        self, conn, ausleihe_repo, gegenstand_repo, kategorie_repo, einweisung_repo, audit_log_repo, clock, vormerkung_repo
    ):
        """BR-VER-02: aktiv → abgeschlossen_verloren."""
        # Setup: Gegenstand
        _gegenstand_anlegen(conn, "inv-1", "Cat1", 10000)

        # Setup: Ausleihe ausgeben (aktiv)
        ausleihe_1 = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo, vormerkung_repo, audit_log_repo, clock, "inv-1", "m1"
        )

        # Action: Verlust erfassen
        ergebnis = verlust_erfassen(
            conn, ausleihe_repo, gegenstand_repo, audit_log_repo, clock, ausleihe_1.ausleihe_id, "wart"
        )

        # Assert: Rückgabe ist Ausleihe (Happy Path)
        assert hasattr(ergebnis, "zustand")
        assert ergebnis.zustand == AusleiheZustand.ABGESCHLOSSEN_VERLOREN

    def test_verlust_erfassen_gegenstand_zustand_uebergang(
        self, conn, ausleihe_repo, gegenstand_repo, kategorie_repo, einweisung_repo, audit_log_repo, clock, vormerkung_repo
    ):
        """BR-VER-03: Gegenstand → ausgemustert."""
        # Setup: Gegenstand
        _gegenstand_anlegen(conn, "inv-1", "Cat1", 10000)

        # Setup: Ausleihe ausgeben
        ausleihe_1 = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo, vormerkung_repo, audit_log_repo, clock, "inv-1", "m1"
        )

        # Action: Verlust erfassen
        verlust_erfassen(
            conn, ausleihe_repo, gegenstand_repo, audit_log_repo, clock, ausleihe_1.ausleihe_id, "wart"
        )

        # Assert: Gegenstand ist ausgemustert
        gegenstand = gegenstand_repo.find_by_inventarnummer("inv-1")
        assert gegenstand.zustand == GegenstandZustand.AUSGEMUSTERT

    def test_verlust_erfassen_kaution_bewegung_erstellt(
        self, conn, ausleihe_repo, gegenstand_repo, kategorie_repo, einweisung_repo, audit_log_repo, clock, vormerkung_repo
    ):
        """BR-KAU-03/04: Kautionsbewegung mit vollständiger Einzug."""
        # Setup: Gegenstand mit WBW 50 EUR (5000 Cent)
        # Kaution = 20% * 5000 = 1000 Cent (10 EUR)
        _gegenstand_anlegen(conn, "inv-1", "Cat1", 5000)

        # Setup: Ausleihe ausgeben
        ausleihe_1 = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo, vormerkung_repo, audit_log_repo, clock, "inv-1", "m1"
        )
        # Kaution sollte 1000 Cent sein (20% von 5000)
        assert ausleihe_1.kaution_cent == 1000  # BR-KAT-04: 20% auf ganze Euro

        # Action: Verlust erfassen
        verlust_erfassen(
            conn, ausleihe_repo, gegenstand_repo, audit_log_repo, clock, ausleihe_1.ausleihe_id, "wart"
        )

        # Assert: Kautionsbewegung existiert mit korrektem Betrag (100% Einzug)
        cursor = conn.execute(
            "SELECT art, betrag_cent, ausloeser FROM kautionsbewegung WHERE ausleihe_id = ?",
            (ausleihe_1.ausleihe_id,),
        )
        row = cursor.fetchone()
        assert row is not None
        art, betrag_cent, ausloeser = row
        assert art == "verlust_einzug"
        assert betrag_cent == 1000  # 100% der Kaution einbehalten
        assert ausloeser == "wart"

    def test_verlust_erfassen_timestamp(
        self, conn, ausleihe_repo, gegenstand_repo, kategorie_repo, einweisung_repo, audit_log_repo, clock, vormerkung_repo
    ):
        """Kautionsbewegung hat Timestamp."""
        # Setup
        _gegenstand_anlegen(conn, "inv-1", "Cat1", 5000)
        ausleihe_1 = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo, vormerkung_repo, audit_log_repo, clock, "inv-1", "m1"
        )

        # Action
        verlust_erfassen(
            conn, ausleihe_repo, gegenstand_repo, audit_log_repo, clock, ausleihe_1.ausleihe_id, "wart"
        )

        # Assert: zeitstempel ist gesetzt
        cursor = conn.execute(
            "SELECT zeitstempel FROM kautionsbewegung WHERE ausleihe_id = ?",
            (ausleihe_1.ausleihe_id,),
        )
        row = cursor.fetchone()
        assert row[0] == clock.jetzt()


class TestVerlustRestEndpoint:
    """UC-06: REST-Layer (Rollenschutz, HTTP-Contract)."""

    @pytest.fixture
    def client(self, conn, clock):
        app = create_app(conn, clock)
        return TestClient(app)

    def _setup_ausleihe(self, conn, ausleihe_repo, gegenstand_repo, kategorie_repo, einweisung_repo, audit_log_repo, vormerkung_repo, clock):
        """Hilfsfunktion: Gegenstand + aktive Ausleihe."""
        # Gegenstand
        _gegenstand_anlegen(conn, "WT-001", "Werkzeug", 20000)

        # Ausleihe ausgeben
        ausleihe_1 = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo, vormerkung_repo, audit_log_repo, clock, "WT-001", "m42"
        )
        return ausleihe_1.ausleihe_id

    def test_verlust_erfassen_erfolg(self, client, conn, ausleihe_repo, gegenstand_repo, kategorie_repo, einweisung_repo, audit_log_repo, vormerkung_repo, clock):
        """POST /ausleihen/{id}/verlust mit wart-Rolle → 201."""
        ausleihe_id = self._setup_ausleihe(conn, ausleihe_repo, gegenstand_repo, kategorie_repo, einweisung_repo, audit_log_repo, vormerkung_repo, clock)

        # Action
        response = client.post(
            f"/ausleihen/{ausleihe_id}/verlust",
            headers={"X-Rolle": "wart"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["zustand"] == "abgeschlossen_verloren"
        assert data["ausleiheId"] == ausleihe_id

    def test_verlust_erfassen_ausleihe_nicht_gefunden(self, client, conn, clock):
        """POST /ausleihen/{id}/verlust mit ungültigem ID → 404."""
        response = client.post(
            "/ausleihen/nichtexistent/verlust",
            headers={"X-Rolle": "wart"},
        )

        assert response.status_code == 404
        assert response.json()["detail"]["fehlercode"] == "AUSLEIHE_NICHT_GEFUNDEN"

    def test_verlust_erfassen_ausleihe_nicht_aktiv(self, client, conn, ausleihe_repo, gegenstand_repo, kategorie_repo, einweisung_repo, audit_log_repo, vormerkung_repo, clock):
        """POST /ausleihen/{id}/verlust auf nicht-aktive Ausleihe → 409."""
        # Setup + Manuelles Zustand-Update
        ausleihe_id = self._setup_ausleihe(conn, ausleihe_repo, gegenstand_repo, kategorie_repo, einweisung_repo, audit_log_repo, vormerkung_repo, clock)
        conn.execute(
            "UPDATE ausleihe SET zustand = ? WHERE ausleihe_id = ?",
            (AusleiheZustand.ABGESCHLOSSEN.value, ausleihe_id),
        )
        conn.commit()

        response = client.post(
            f"/ausleihen/{ausleihe_id}/verlust",
            headers={"X-Rolle": "wart"},
        )

        assert response.status_code == 409
        assert response.json()["detail"]["fehlercode"] == "AUSLEIHE_NICHT_AKTIV"

    def test_verlust_erfassen_rolle_erforderlich(self, client, conn, ausleihe_repo, gegenstand_repo, kategorie_repo, einweisung_repo, audit_log_repo, vormerkung_repo, clock):
        """POST /ausleihen/{id}/verlust ohne wart-Rolle → 403."""
        ausleihe_id = self._setup_ausleihe(conn, ausleihe_repo, gegenstand_repo, kategorie_repo, einweisung_repo, audit_log_repo, vormerkung_repo, clock)

        # Anfrage mit falscher Rolle (z.B. "mitglied" statt "wart")
        response = client.post(
            f"/ausleihen/{ausleihe_id}/verlust",
            headers={"X-Rolle": "mitglied"},
        )

        assert response.status_code == 403
