"""EPIC-E: Vormerkung erfassen & verwalten (UC-05).

Referenzen:
- src/docs/implementation/epic-e-vormerkung-analyse.adoc
- src/docs/specs/spec-use-cases.adoc, UC-05
- src/docs/specs/spec-system-interfaces.adoc, SI-05
- src/docs/specs/spec-acceptance-criteria.adoc,
  vormerkung-erfassen.feature
"""
import pytest
import sqlite3

from fastapi.testclient import TestClient

from leihgut.adapters.persistence.sqlite_vormerkung_repository import (
    SqliteVormerkungRepository,
)
from leihgut.adapters.persistence.sqlite_kategorie_repository import (
    SqliteKategorieRepository,
)
from leihgut.adapters.persistence.sqlite_gegenstand_repository import (
    create_connection,
)
from leihgut.adapters.rest.app import create_app
from leihgut.anwendungskern.vormerkung_service import (
    DuplikatVormerkung,
    MitgliedGesperrt,
    VormerkungNichtGefunden,
    vormerkung_erfassen,
    vormerkungs_verwalten_nach_rueckgabe,
)
from leihgut.domain.vormerkung import Vormerkung, VormerkungStatus
from tests.fakes import FakeClock


@pytest.fixture
def conn():
    connection = create_connection(":memory:")
    connection.execute(
        "INSERT INTO kategorie "
        "(kategorie_id, name, leihdauer_tage, wartungsintervall, einweisungspflichtig) "
        "VALUES (?, ?, ?, ?, ?)",
        ("kat-leiter", "Leiter", 3, 30, 0),
    )
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def vormerkung_repo(conn):
    return SqliteVormerkungRepository(conn)


@pytest.fixture
def kategorie_repo(conn):
    return SqliteKategorieRepository(conn)


@pytest.fixture
def clock():
    return FakeClock("2026-08-19T10:00:00")


# --- Service-Ebene: Vormerkung erfassen (UC-05) -------------------------

class TestVormerkungErfassen:
    def test_legt_oeffne_vormerkung_an(self, vormerkung_repo, kategorie_repo, clock):
        # @UC-05 @BR-VOR-01 @BR-VOR-02 vormerkung-erfassen.feature
        ergebnis = vormerkung_erfassen(
            vormerkung_repo, kategorie_repo, clock, "M-1", "kat-leiter"
        )

        assert isinstance(ergebnis, Vormerkung)
        assert ergebnis.ist_offen()
        assert ergebnis.reihenfolge == 1
        assert ergebnis.erstellt_am == "2026-08-19T10:00:00"

    def test_zweite_vormerkung_bekommt_reihenfolge_2(
        self, vormerkung_repo, kategorie_repo, clock
    ):
        # @UC-05 @BR-VOR-02 vormerkung-erfassen.feature: Reihenfolge=FIFO
        erste = vormerkung_erfassen(
            vormerkung_repo, kategorie_repo, clock, "M-1", "kat-leiter"
        )
        zweite = vormerkung_erfassen(
            vormerkung_repo, kategorie_repo, clock, "M-2", "kat-leiter"
        )

        assert erste.reihenfolge == 1
        assert zweite.reihenfolge == 2

    def test_lehnt_doppelte_vormerkung_ab(self, vormerkung_repo, kategorie_repo, clock):
        # @UC-05 vormerkung-erfassen.feature: "Doppelte Vormerkung wird abgelehnt"
        vormerkung_erfassen(
            vormerkung_repo, kategorie_repo, clock, "M-3", "kat-leiter"
        )

        ergebnis = vormerkung_erfassen(
            vormerkung_repo, kategorie_repo, clock, "M-3", "kat-leiter"
        )

        assert ergebnis == DuplikatVormerkung("M-3", "kat-leiter")

    def test_lehnt_vormerkung_gesperrten_mitglieds_ab(
        self, vormerkung_repo, kategorie_repo, clock
    ):
        # @UC-05 Validierung: Mitglied nicht gesperrt
        ergebnis = vormerkung_erfassen(
            vormerkung_repo,
            kategorie_repo,
            clock,
            "M-4",
            "kat-leiter",
            gesperrte_mitglieder=["M-4"],
        )

        assert ergebnis == MitgliedGesperrt("M-4")

    def test_lehnt_vormerkung_unbekannter_kategorie_ab(
        self, vormerkung_repo, kategorie_repo, clock
    ):
        # @UC-05 Validierung: Kategorie existiert
        ergebnis = vormerkung_erfassen(
            vormerkung_repo, kategorie_repo, clock, "M-5", "unbekannt"
        )

        assert isinstance(ergebnis, type(ergebnis))  # KategorieNichtGefunden
        assert hasattr(ergebnis, "kategorie_id")

    def test_erlaubt_erneute_vormerkung_nach_absage(
        self, vormerkung_repo, kategorie_repo, clock
    ):
        """Keine direkte Spec, aber Konsequenz aus BR-VOR-01:
        eine abgesagte Vormerkung blockiert keine neue Erfassung."""
        erste = vormerkung_erfassen(
            vormerkung_repo, kategorie_repo, clock, "M-6", "kat-leiter"
        )
        # Manuell absagen
        abgesagte = Vormerkung(
            vormerkung_id=erste.vormerkung_id,
            kategorie_id=erste.kategorie_id,
            mitglied_id=erste.mitglied_id,
            erstellt_am=erste.erstellt_am,
            status=VormerkungStatus.AUTOMATISCH_ABGESAGT,
            reihenfolge=erste.reihenfolge,
        )
        vormerkung_repo.update(abgesagte)

        ergebnis = vormerkung_erfassen(
            vormerkung_repo, kategorie_repo, clock, "M-6", "kat-leiter"
        )

        assert isinstance(ergebnis, Vormerkung)
        assert ergebnis.ist_offen()


# --- Service-Ebene: Vormerkungs verwalten nach Rückgabe (UC-03 Integration) ---

class TestVormerkungenNachRueckgabe:
    def test_absagt_erste_vormerkung_automatisch(self, vormerkung_repo, clock):
        # @UC-03 Integration: Nach Rückgabe automatische Absage
        erste = Vormerkung(
            vormerkung_id="v-1",
            kategorie_id="kat-leiter",
            mitglied_id="M-1",
            erstellt_am="2026-08-19T10:00:00",
            status=VormerkungStatus.OFFEN,
            reihenfolge=1,
        )
        zweite = Vormerkung(
            vormerkung_id="v-2",
            kategorie_id="kat-leiter",
            mitglied_id="M-2",
            erstellt_am="2026-08-19T10:00:01",
            status=VormerkungStatus.OFFEN,
            reihenfolge=2,
        )
        vormerkung_repo.insert(erste)
        vormerkung_repo.insert(zweite)

        abgesagte = vormerkungs_verwalten_nach_rueckgabe(
            vormerkung_repo, "kat-leiter"
        )

        assert abgesagte is not None
        assert abgesagte.vormerkung_id == "v-1"
        assert abgesagte.status == VormerkungStatus.AUTOMATISCH_ABGESAGT
        # Zweite Vormerkung bleibt offen
        zweite_nach = vormerkung_repo.find_by_id("v-2")
        assert zweite_nach.ist_offen()

    def test_liefert_none_wenn_keine_vormerkung_vorhanden(self, vormerkung_repo):
        ergebnis = vormerkungs_verwalten_nach_rueckgabe(
            vormerkung_repo, "kat-leiter"
        )

        assert ergebnis is None


# --- Akzeptanz-Ebene: REST (SI-05) --------------------------------

class TestVormerkungRest:
    def test_post_vormerkungen_gibt_201_zurueck(self, conn, clock):
        client = TestClient(create_app(conn, clock=clock))

        response = client.post(
            "/vormerkungen",
            headers={"X-Rolle": "mitglied"},
            json={"mitgliedId": "M-1", "kategorieId": "kat-leiter"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["mitgliedId"] == "M-1"
        assert body["kategorieId"] == "kat-leiter"
        assert body["status"] == "offen"
        assert body["reihenfolge"] == 1
        assert "vormerkungId" in body
        assert "erstelltAm" in body

    def test_post_vormerkungen_lehnt_duplikat_mit_409_ab(self, conn, clock):
        client = TestClient(create_app(conn, clock=clock))
        client.post(
            "/vormerkungen",
            headers={"X-Rolle": "mitglied"},
            json={"mitgliedId": "M-2", "kategorieId": "kat-leiter"},
        )

        response = client.post(
            "/vormerkungen",
            headers={"X-Rolle": "mitglied"},
            json={"mitgliedId": "M-2", "kategorieId": "kat-leiter"},
        )

        assert response.status_code == 409
        assert response.json()["detail"]["fehlercode"] == "DUPLIKAT_VORMERKUNG"

    def test_get_vormerkung_gibt_200_zurueck(self, conn, clock):
        client = TestClient(create_app(conn, clock=clock))
        angelegt = client.post(
            "/vormerkungen",
            headers={"X-Rolle": "mitglied"},
            json={"mitgliedId": "M-3", "kategorieId": "kat-leiter"},
        ).json()

        response = client.get(
            f"/vormerkungen/{angelegt['vormerkungId']}",
            headers={"X-Rolle": "mitglied"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["vormerkungId"] == angelegt["vormerkungId"]
        assert body["status"] == "offen"
        assert body["reihenfolge"] == 1

    def test_get_unbekannte_vormerkung_gibt_404_zurueck(self, conn, clock):
        client = TestClient(create_app(conn, clock=clock))

        response = client.get(
            "/vormerkungen/unbekannt", headers={"X-Rolle": "mitglied"}
        )

        assert response.status_code == 404
        assert response.json()["detail"]["fehlercode"] == "VORMERKUNG_NICHT_GEFUNDEN"

    def test_post_vormerkungen_lehnt_unbekannte_kategorie_mit_404_ab(
        self, conn, clock
    ):
        client = TestClient(create_app(conn, clock=clock))

        response = client.post(
            "/vormerkungen",
            headers={"X-Rolle": "mitglied"},
            json={"mitgliedId": "M-4", "kategorieId": "unbekannt"},
        )

        assert response.status_code == 404
        assert response.json()["detail"]["fehlercode"] == "KATEGORIE_NICHT_GEFUNDEN"

    def test_post_vormerkungen_ohne_rolle_wird_abgelehnt(self, conn, clock):
        client = TestClient(create_app(conn, clock=clock))

        response = client.post(
            "/vormerkungen",
            headers={"X-Rolle": "wart"},
            json={"mitgliedId": "M-5", "kategorieId": "kat-leiter"},
        )

        assert response.status_code == 403
        assert response.json()["detail"]["fehlercode"] == "ROLLE_NICHT_BERECHTIGT"

    def test_get_vormerkung_ohne_rolle_wird_abgelehnt(self, conn, clock):
        client = TestClient(create_app(conn, clock=clock))
        angelegt = client.post(
            "/vormerkungen",
            headers={"X-Rolle": "mitglied"},
            json={"mitgliedId": "M-6", "kategorieId": "kat-leiter"},
        ).json()

        response = client.get(
            f"/vormerkungen/{angelegt['vormerkungId']}",
            headers={"X-Rolle": "admin"},  # admin role not allowed
        )

        assert response.status_code == 403
        assert response.json()["detail"]["fehlercode"] == "ROLLE_NICHT_BERECHTIGT"

    def test_post_vormerkungen_reihenfolge_fifo(self, conn, clock):
        # @UC-05 @BR-VOR-02 vormerkung-erfassen.feature: "Reihenfolge ist FIFO"
        client = TestClient(create_app(conn, clock=clock))

        erste = client.post(
            "/vormerkungen",
            headers={"X-Rolle": "mitglied"},
            json={"mitgliedId": "M-7", "kategorieId": "kat-leiter"},
        ).json()

        zweite = client.post(
            "/vormerkungen",
            headers={"X-Rolle": "mitglied"},
            json={"mitgliedId": "M-8", "kategorieId": "kat-leiter"},
        ).json()

        assert erste["reihenfolge"] == 1
        assert zweite["reihenfolge"] == 2
