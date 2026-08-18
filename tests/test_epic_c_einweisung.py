"""EPIC-C: Einweisung erfassen/widerrufen (UC-07/UC-08).

Referenzen:
- src/docs/implementation/epic-c-einweisung.adoc
- src/docs/specs/spec-use-cases.adoc, UC-07, UC-08
- src/docs/specs/spec-system-interfaces.adoc, SI-07, SI-08
- src/docs/specs/spec-acceptance-criteria.adoc,
  einweisung-erfassen.feature, einweisung-widerrufen.feature

BR-AUS-04 (Ausgabe-Ablehnung bei fehlender/widerrufener Einweisung) wird
hier bewusst nicht als Ende-zu-Ende-Szenario nachgebildet — das setzt den
Ausgabe-Anwendungsdienst aus EPIC-A voraus. Hier wird nur geprüft, dass die
Einweisung nach Widerruf tatsächlich als ungültig gilt
(`Einweisung.ist_gueltig()` bzw. `find_gueltige` liefert `None`), was die
Grundlage für die BR-AUS-04-Prüfung in EPIC-A ist.
"""
import pytest
import sqlite3
from datetime import datetime

from fastapi.testclient import TestClient

from leihgut.adapters.persistence.sqlite_einweisung_repository import (
    SqliteEinweisungRepository,
)
from leihgut.adapters.persistence.sqlite_kategorie_repository import (
    SqliteKategorieRepository,
)
from leihgut.adapters.persistence.sqlite_gegenstand_repository import (
    create_connection,
)
from leihgut.adapters.rest.app import create_app
from leihgut.anwendungskern.einweisung_service import (
    BereitsWiderrufen,
    EinweisungBestehtBereits,
    EinweisungNichtGefunden,
    einweisung_erfassen,
    einweisung_widerrufen,
)
from leihgut.domain.einweisung import Einweisung
from tests.fakes import FakeClock


@pytest.fixture
def conn():
    connection = create_connection(":memory:")
    connection.execute(
        "INSERT INTO kategorie "
        "(kategorie_id, name, leihdauer_tage, wartungsintervall, einweisungspflichtig) "
        "VALUES (?, ?, ?, ?, ?)",
        ("kat-kettensaege", "Kettensaege", 7, 20, 1),
    )
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def einweisung_repo(conn):
    return SqliteEinweisungRepository(conn)


@pytest.fixture
def clock():
    return FakeClock("2026-08-18T10:00:00")


# --- Service-Ebene: Einweisung erfassen (UC-07) -------------------------

class TestEinweisungErfassen:
    def test_legt_unbefristete_einweisung_an(self, einweisung_repo, clock):
        # @UC-07 @BR-EIN-01 @BR-EIN-02 einweisung-erfassen.feature
        ergebnis = einweisung_erfassen(
            einweisung_repo, clock, "M-7", "kat-kettensaege"
        )

        assert isinstance(ergebnis, Einweisung)
        assert ergebnis.ist_gueltig()
        assert ergebnis.erstellt_am == "2026-08-18T10:00:00"
        gefunden = einweisung_repo.find_gueltige("M-7", "kat-kettensaege")
        assert gefunden == ergebnis

    def test_lehnt_doppelte_einweisung_ab(self, einweisung_repo, clock):
        # @UC-07 einweisung-erfassen.feature: "Doppelte Einweisung wird abgelehnt"
        einweisung_erfassen(einweisung_repo, clock, "M-8", "kat-kettensaege")

        ergebnis = einweisung_erfassen(
            einweisung_repo, clock, "M-8", "kat-kettensaege"
        )

        assert ergebnis == EinweisungBestehtBereits("M-8", "kat-kettensaege")

    def test_erlaubt_erneute_einweisung_nach_widerruf(self, einweisung_repo, clock):
        """Kein direktes Feature-Szenario, aber Konsequenz aus BR-EIN-02/03:
        eine widerrufene Einweisung blockiert keine neue Erfassung."""
        erste = einweisung_erfassen(einweisung_repo, clock, "M-8", "kat-kettensaege")
        einweisung_widerrufen(einweisung_repo, clock, erste.einweisung_id)

        ergebnis = einweisung_erfassen(
            einweisung_repo, clock, "M-8", "kat-kettensaege"
        )

        assert isinstance(ergebnis, Einweisung)


class TestSystemClock:
    """Smoke-Test der Produktionsimplementierung (ADR-006) — die
    Anwendungsdienste selbst werden überall mit `FakeClock` getestet."""

    def test_liefert_iso_zeitstempel_ohne_mikrosekunden(self):
        from leihgut.adapters.system_clock import SystemClock

        zeitstempel = SystemClock().jetzt()

        datetime.fromisoformat(zeitstempel)
        assert "." not in zeitstempel


class TestEinweisungUniqueIndex:
    """BR-EIN-01: Der partielle Unique-Index in schema.sql greift auch dann,
    wenn (theoretisch) am Anwendungsdienst vorbei direkt in die Tabelle
    geschrieben würde — DB-erzwungene zweite Schranke, analog zu ADR-007."""

    def test_zweite_gueltige_einweisung_derselben_kombination_schlaegt_fehl(
        self, conn
    ):
        conn.execute(
            "INSERT INTO einweisung (einweisung_id, mitglied_id, kategorie_id, erstellt_am) "
            "VALUES (?, ?, ?, ?)",
            ("E-1", "M-1", "kat-kettensaege", "2026-08-18T10:00:00"),
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO einweisung (einweisung_id, mitglied_id, kategorie_id, erstellt_am) "
                "VALUES (?, ?, ?, ?)",
                ("E-2", "M-1", "kat-kettensaege", "2026-08-18T11:00:00"),
            )


# --- Service-Ebene: Einweisung widerrufen (UC-08) -----------------------

class TestEinweisungWiderrufen:
    def test_widerruft_gueltige_einweisung(self, einweisung_repo, clock):
        # @UC-08 @BR-EIN-03 einweisung-widerrufen.feature
        angelegt = einweisung_erfassen(
            einweisung_repo, clock, "M-9", "kat-kettensaege"
        )

        ergebnis = einweisung_widerrufen(einweisung_repo, clock, angelegt.einweisung_id)

        assert isinstance(ergebnis, Einweisung)
        assert not ergebnis.ist_gueltig()
        assert einweisung_repo.find_gueltige("M-9", "kat-kettensaege") is None

    def test_lehnt_widerruf_unbekannter_einweisung_ab(self, einweisung_repo, clock):
        ergebnis = einweisung_widerrufen(einweisung_repo, clock, "unbekannt")

        assert ergebnis == EinweisungNichtGefunden("unbekannt")

    def test_lehnt_erneuten_widerruf_ab(self, einweisung_repo, clock):
        # @UC-08 einweisung-widerrufen.feature: "Erneuter Widerruf ... wird abgelehnt"
        angelegt = einweisung_erfassen(
            einweisung_repo, clock, "M-1", "kat-kettensaege"
        )
        einweisung_widerrufen(einweisung_repo, clock, angelegt.einweisung_id)

        ergebnis = einweisung_widerrufen(einweisung_repo, clock, angelegt.einweisung_id)

        assert ergebnis == BereitsWiderrufen(angelegt.einweisung_id)


# --- Akzeptanz-Ebene: REST (SI-07/SI-08) --------------------------------

class TestEinweisungRest:
    def test_post_einweisungen_gibt_201_zurueck(self, conn, clock):
        client = TestClient(create_app(conn, clock=clock))

        response = client.post(
            "/einweisungen",
            headers={"X-Rolle": "wart"},
            json={"mitgliedId": "M-7", "kategorieId": "kat-kettensaege"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["mitgliedId"] == "M-7"
        assert body["kategorieId"] == "kat-kettensaege"
        assert body["erstelltAm"] == "2026-08-18T10:00:00"
        assert "einweisungId" in body

    def test_post_einweisungen_lehnt_duplikat_mit_409_ab(self, conn, clock):
        client = TestClient(create_app(conn, clock=clock))
        client.post(
            "/einweisungen",
            headers={"X-Rolle": "wart"},
            json={"mitgliedId": "M-8", "kategorieId": "kat-kettensaege"},
        )

        response = client.post(
            "/einweisungen",
            headers={"X-Rolle": "wart"},
            json={"mitgliedId": "M-8", "kategorieId": "kat-kettensaege"},
        )

        assert response.status_code == 409
        assert response.json()["detail"]["fehlercode"] == "EINWEISUNG_BESTEHT_BEREITS"

    def test_delete_einweisung_gibt_204_zurueck(self, conn, clock):
        client = TestClient(create_app(conn, clock=clock))
        angelegt = client.post(
            "/einweisungen",
            headers={"X-Rolle": "wart"},
            json={"mitgliedId": "M-9", "kategorieId": "kat-kettensaege"},
        ).json()

        response = client.delete(
            f"/einweisungen/{angelegt['einweisungId']}",
            headers={"X-Rolle": "wart"},
        )

        assert response.status_code == 204

    def test_delete_unbekannte_einweisung_gibt_404_zurueck(self, conn, clock):
        client = TestClient(create_app(conn, clock=clock))

        response = client.delete(
            "/einweisungen/unbekannt", headers={"X-Rolle": "wart"}
        )

        assert response.status_code == 404
        assert response.json()["detail"]["fehlercode"] == "EINWEISUNG_NICHT_GEFUNDEN"

    def test_delete_bereits_widerrufene_einweisung_gibt_409_zurueck(self, conn, clock):
        # @UC-08 einweisung-widerrufen.feature: "Erneuter Widerruf ... wird abgelehnt"
        client = TestClient(create_app(conn, clock=clock))
        angelegt = client.post(
            "/einweisungen",
            headers={"X-Rolle": "wart"},
            json={"mitgliedId": "M-1", "kategorieId": "kat-kettensaege"},
        ).json()
        client.delete(
            f"/einweisungen/{angelegt['einweisungId']}", headers={"X-Rolle": "wart"}
        )

        response = client.delete(
            f"/einweisungen/{angelegt['einweisungId']}", headers={"X-Rolle": "wart"}
        )

        assert response.status_code == 409
        assert response.json()["detail"]["fehlercode"] == "BEREITS_WIDERRUFEN"

    def test_post_einweisungen_ohne_rolle_wird_abgelehnt(self, conn, clock):
        client = TestClient(create_app(conn, clock=clock))

        response = client.post(
            "/einweisungen",
            headers={"X-Rolle": "mitglied"},
            json={"mitgliedId": "M-7", "kategorieId": "kat-kettensaege"},
        )

        assert response.status_code == 403
        assert response.json()["detail"]["fehlercode"] == "ROLLE_NICHT_BERECHTIGT"
