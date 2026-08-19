"""Test-Suite für UC-05 (Wartung abschließen) / SI-06.

Tests folgen Hamburg-Style TDD:
1. Service-Validierungen (Operation, keine Ports)
2. Service-Happy-Path (Integration, mit Repositories)
3. REST-Endpoints (API-Kontrakt)
"""
import uuid
from datetime import date
import pytest
from starlette.testclient import TestClient

from leihgut.adapters.persistence.sqlite_gegenstand_repository import (
    create_connection,
)
from leihgut.adapters.persistence.sqlite_kategorie_repository import (
    SqliteKategorieRepository,
)
from leihgut.adapters.persistence.sqlite_gegenstand_repository import (
    SqliteGegenstandRepository,
)
from leihgut.adapters.persistence.sqlite_vormerkung_repository import (
    SqliteVormerkungRepository,
)
from leihgut.adapters.rest.app import create_app
from leihgut.anwendungskern.wartung_service import (
    wartung_abschliessen,
    GegenstandNichtGefunden,
    NichtWartungsfaellig,
)
from leihgut.domain.gegenstand import Gegenstand, GegenstandZustand
from leihgut.domain.kategorie import Kategorie
from leihgut.domain.vormerkung import Vormerkung, VormerkungStatus
from leihgut.ports.clock import Clock


class FakeClock(Clock):
    def __init__(self, now: str = "2024-08-19T10:00:00Z"):
        self.now = now

    def jetzt(self) -> str:
        return self.now


@pytest.fixture
def conn():
    """In-Memory SQLite für Tests."""
    connection = create_connection(":memory:")
    # Setup: Test-Kategorien
    connection.execute(
        """
        INSERT INTO kategorie (
            kategorie_id, name, leihdauer_tage, 
            wartungsintervall, einweisungspflichtig
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        ("KAT-001", "Test-Kategorie-1", 14, 3, False),
    )
    connection.execute(
        """
        INSERT INTO kategorie (
            kategorie_id, name, leihdauer_tage, 
            wartungsintervall, einweisungspflichtig
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        ("KAT-REST-001", "REST-Test-Kategorie-1", 14, 3, False),
    )
    connection.execute(
        """
        INSERT INTO kategorie (
            kategorie_id, name, leihdauer_tage, 
            wartungsintervall, einweisungspflichtig
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        ("KAT-REST-002", "REST-Test-Kategorie-2", 14, 3, False),
    )
    connection.execute(
        """
        INSERT INTO kategorie (
            kategorie_id, name, leihdauer_tage, 
            wartungsintervall, einweisungspflichtig
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        ("KAT-REST-003", "REST-Test-Kategorie-3", 14, 3, False),
    )
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def gegenstand_repo(conn):
    return SqliteGegenstandRepository(conn)


@pytest.fixture
def kategorie_repo(conn):
    return SqliteKategorieRepository(conn)


@pytest.fixture
def vormerkung_repo(conn):
    return SqliteVormerkungRepository(conn)


@pytest.fixture
def clock():
    return FakeClock("2026-08-19T12:00:00Z")


def _gegenstand_anlegen(
    conn,
    inventarnummer: str,
    kategorie_id: str,
    zustand: GegenstandZustand = GegenstandZustand.VERFUEGBAR,
    nutzungszaehler: int = 0,
    wiederbeschaffungswert_cent: int = 10000,
) -> None:
    """Helper: Direkt Gegenstand in DB einfügen (Umgeht Service)."""
    conn.execute(
        """
        INSERT INTO gegenstand (
            inventarnummer, kategorie_id, zustand, 
            wiederbeschaffungswert_cent, nutzungszaehler
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            inventarnummer,
            kategorie_id,
            zustand.value,
            wiederbeschaffungswert_cent,
            nutzungszaehler,
        ),
    )
    conn.commit()


def _kategorie_anlegen(
    conn,
    kategorie_id: str,
    name: str = "Test-Kategorie",
    leihdauer_tage: int = 14,
    wartungsintervall: int = 3,
    einweisungspflichtig: bool = False,
) -> None:
    """Helper: Direkt Kategorie in DB einfügen."""
    conn.execute(
        """
        INSERT INTO kategorie (
            kategorie_id, name, leihdauer_tage, 
            wartungsintervall, einweisungspflichtig
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            kategorie_id,
            name,
            leihdauer_tage,
            wartungsintervall,
            einweisungspflichtig,
        ),
    )
    conn.commit()


def _vormerkung_anlegen(
    conn,
    vormerkung_id: str,
    kategorie_id: str,
    mitglied_id: str,
    status: VormerkungStatus = VormerkungStatus.OFFEN,
    reihenfolge: int = 1,
) -> None:
    """Helper: Direkt Vormerkung in DB einfügen."""
    conn.execute(
        """
        INSERT INTO vormerkung (
            vormerkung_id, kategorie_id, mitglied_id, 
            erstellt_am, status, reihenfolge
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            vormerkung_id,
            kategorie_id,
            mitglied_id,
            "2024-08-01T00:00:00Z",
            status.value,
            reihenfolge,
        ),
    )
    conn.commit()


# ============================================================================
# TEST CLASS 1: Service Validierungen (kein Port-Zugriff außer Reads)
# ============================================================================


class TestWartungServiceValidierung:
    """Validierungsregeln für UC-05."""

    def test_gegenstand_nicht_gefunden(self, gegenstand_repo, kategorie_repo, vormerkung_repo):
        """REQ-UC05-01: Gegenstand nicht vorhanden → 404."""
        result = wartung_abschliessen(
            gegenstand_repo=gegenstand_repo,
            kategorie_repo=kategorie_repo,
            vormerkung_repo=vormerkung_repo,
            inventarnummer="NICHT_VORHANDEN",
        )

        assert isinstance(result, GegenstandNichtGefunden)
        assert result.inventarnummer == "NICHT_VORHANDEN"

    def test_gegenstand_nicht_wartungsfaellig(
        self, conn, gegenstand_repo, kategorie_repo, vormerkung_repo
    ):
        """REQ-UC05-01: Gegenstand nicht wartungsfällig → 409."""
        inventarnummer = "INV-001"
        kategorie_id = "KAT-001"

        _gegenstand_anlegen(
            conn,
            inventarnummer,
            kategorie_id,
            zustand=GegenstandZustand.VERFUEGBAR,  # nicht wartungsfaellig
        )

        result = wartung_abschliessen(
            gegenstand_repo=gegenstand_repo,
            kategorie_repo=kategorie_repo,
            vormerkung_repo=vormerkung_repo,
            inventarnummer=inventarnummer,
        )

        assert isinstance(result, NichtWartungsfaellig)
        assert result.inventarnummer == inventarnummer


# ============================================================================
# TEST CLASS 2: Service Happy Path
# ============================================================================


class TestWartungServiceHappyPath:
    """Erfolgreiche Wartungsabschlüsse."""

    def test_wartung_ohne_vormerkung_verfuegbar(
        self, conn, gegenstand_repo, kategorie_repo, vormerkung_repo
    ):
        """Wartung abschließen ohne Vormerkung → Gegenstand verfügbar."""
        kategorie_id = "KAT-001"
        inventarnummer = "INV-001"

        _gegenstand_anlegen(
            conn,
            inventarnummer,
            kategorie_id,
            zustand=GegenstandZustand.WARTUNGSFAELLIG,
            nutzungszaehler=3,
        )

        result = wartung_abschliessen(
            gegenstand_repo=gegenstand_repo,
            kategorie_repo=kategorie_repo,
            vormerkung_repo=vormerkung_repo,
            inventarnummer=inventarnummer,
        )

        # Validiere Erfolg
        from leihgut.anwendungskern.wartung_service import WartungErgebnis
        assert isinstance(result, WartungErgebnis)
        assert result.inventarnummer == inventarnummer
        assert result.zustand == GegenstandZustand.VERFUEGBAR
        assert result.nutzungszaehler == 0

        # Validiere DB-Zustand
        gegenstand = gegenstand_repo.find_by_inventarnummer(inventarnummer)
        assert gegenstand.zustand == GegenstandZustand.VERFUEGBAR
        assert gegenstand.nutzungszaehler == 0

    def test_wartung_mit_vormerkung_reserviert(
        self, conn, gegenstand_repo, kategorie_repo, vormerkung_repo
    ):
        """Wartung mit offener Vormerkung → Gegenstand reserviert."""
        kategorie_id = "KAT-001"
        inventarnummer = "INV-001"
        vormerkung_id = str(uuid.uuid4())
        mitglied_id = "M001"

        _gegenstand_anlegen(
            conn,
            inventarnummer,
            kategorie_id,
            zustand=GegenstandZustand.WARTUNGSFAELLIG,
            nutzungszaehler=5,
        )
        _vormerkung_anlegen(
            conn,
            vormerkung_id,
            kategorie_id,
            mitglied_id,
            status=VormerkungStatus.OFFEN,
            reihenfolge=1,
        )

        result = wartung_abschliessen(
            gegenstand_repo=gegenstand_repo,
            kategorie_repo=kategorie_repo,
            vormerkung_repo=vormerkung_repo,
            inventarnummer=inventarnummer,
        )

        # Validiere Erfolg: Gegenstand RESERVIERT
        from leihgut.anwendungskern.wartung_service import WartungErgebnis
        assert isinstance(result, WartungErgebnis)
        assert result.inventarnummer == inventarnummer
        assert result.zustand == GegenstandZustand.RESERVIERT
        assert result.nutzungszaehler == 0

        # Validiere DB
        gegenstand = gegenstand_repo.find_by_inventarnummer(inventarnummer)
        assert gegenstand.zustand == GegenstandZustand.RESERVIERT
        assert gegenstand.nutzungszaehler == 0

    def test_wartung_nur_erste_vormerkung_reserviert(
        self, conn, gegenstand_repo, kategorie_repo, vormerkung_repo
    ):
        """Bei mehreren Vormerkungen: Nur 1. (reihenfolge=1) reserviert den Gegenstand."""
        kategorie_id = "KAT-001"
        inventarnummer = "INV-001"

        _gegenstand_anlegen(
            conn,
            inventarnummer,
            kategorie_id,
            zustand=GegenstandZustand.WARTUNGSFAELLIG,
            nutzungszaehler=2,
        )

        # Zwei offene Vormerkungen (reihenfolge 1 und 2)
        _vormerkung_anlegen(
            conn, str(uuid.uuid4()), kategorie_id, "M001", VormerkungStatus.OFFEN, 1
        )
        _vormerkung_anlegen(
            conn, str(uuid.uuid4()), kategorie_id, "M002", VormerkungStatus.OFFEN, 2
        )

        result = wartung_abschliessen(
            gegenstand_repo=gegenstand_repo,
            kategorie_repo=kategorie_repo,
            vormerkung_repo=vormerkung_repo,
            inventarnummer=inventarnummer,
        )

        # Gegenstand wird RESERVIERT (1. Vormerkung bindet ihn)
        from leihgut.anwendungskern.wartung_service import WartungErgebnis
        assert isinstance(result, WartungErgebnis)
        assert result.zustand == GegenstandZustand.RESERVIERT
        assert result.nutzungszaehler == 0

        # Vormerkungen bleiben unverändert
        offene = vormerkung_repo.find_offene_je_kategorie_sortiert_nach_reihenfolge(
            kategorie_id
        )
        assert len(offene) == 2
        assert offene[0].reihenfolge == 1
        assert offene[1].reihenfolge == 2


# ============================================================================
# TEST CLASS 3: REST-Endpoints
# ============================================================================


class TestWartungRestEndpoint:
    """REST API Kontrakt für UC-05."""

    @pytest.fixture
    def client(self, conn, clock):
        app = create_app(conn, clock)
        return TestClient(app)

    def test_post_wartungen_erfolg_ohne_vormerkung(self, conn, client):
        """POST /wartungen → 200 VERFUEGBAR."""
        kategorie_id = "KAT-REST-001"
        inventarnummer = "INV-REST-001"

        _gegenstand_anlegen(
            conn,
            inventarnummer,
            kategorie_id,
            zustand=GegenstandZustand.WARTUNGSFAELLIG,
            nutzungszaehler=3,
        )

        # POST /wartungen
        response = client.post(
            "/wartungen",
            json={"inventarnummer": inventarnummer},
            headers={"X-Rolle": "wart"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["inventarnummer"] == inventarnummer
        assert data["zustand"] == "verfuegbar"
        assert data["nutzungszaehler"] == 0

    def test_post_wartungen_erfolg_mit_vormerkung(self, conn, client):
        """POST /wartungen mit Vormerkung → 200 RESERVIERT."""
        kategorie_id = "KAT-REST-002"
        inventarnummer = "INV-REST-002"
        vormerkung_id = str(uuid.uuid4())

        _gegenstand_anlegen(
            conn,
            inventarnummer,
            kategorie_id,
            zustand=GegenstandZustand.WARTUNGSFAELLIG,
            nutzungszaehler=4,
        )
        _vormerkung_anlegen(
            conn,
            vormerkung_id,
            kategorie_id,
            "M-REST-001",
            status=VormerkungStatus.OFFEN,
            reihenfolge=1,
        )

        response = client.post(
            "/wartungen",
            json={"inventarnummer": inventarnummer},
            headers={"X-Rolle": "wart"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["zustand"] == "reserviert"
        assert data["nutzungszaehler"] == 0

    def test_post_wartungen_nicht_gefunden(self, client):
        """POST /wartungen (Gegenstand nicht vorhanden) → 404."""
        response = client.post(
            "/wartungen",
            json={"inventarnummer": "NICHT_VORHANDEN"},
            headers={"X-Rolle": "wart"},
        )

        assert response.status_code == 404
        assert "GEGENSTAND_NICHT_GEFUNDEN" in response.text

    def test_post_wartungen_nicht_wartungsfaellig(self, conn, client):
        """POST /wartungen (nicht wartungsfällig) → 409."""
        kategorie_id = "KAT-REST-003"
        inventarnummer = "INV-REST-003"

        _gegenstand_anlegen(
            conn, inventarnummer, kategorie_id, zustand=GegenstandZustand.VERFUEGBAR
        )

        response = client.post(
            "/wartungen",
            json={"inventarnummer": inventarnummer},
            headers={"X-Rolle": "wart"},
        )

        assert response.status_code == 409
        assert "NICHT_WARTUNGSFAELLIG" in response.text

    def test_post_wartungen_rolle_erforderlich(self, conn, client):
        """POST /wartungen ohne wart-Rolle → 403."""
        kategorie_id = "KAT-REST-001"
        inventarnummer = "INV-REST-999"

        _gegenstand_anlegen(
            conn,
            inventarnummer,
            kategorie_id,
            zustand=GegenstandZustand.WARTUNGSFAELLIG,
            nutzungszaehler=1,
        )

        # Anfrage mit falscher Rolle (z.B. "mitglied" statt "wart")
        response = client.post(
            "/wartungen",
            json={"inventarnummer": inventarnummer},
            headers={"X-Rolle": "mitglied"},
        )

        assert response.status_code == 403
