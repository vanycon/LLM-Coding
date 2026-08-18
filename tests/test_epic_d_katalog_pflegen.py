"""EPIC-D: Katalog pflegen (UC-09/SI-09).

Referenzen:
- src/docs/implementation/epic-d-katalog-verfuegbarkeit.adoc
- src/docs/specs/spec-use-cases.adoc, UC-09
- src/docs/specs/spec-system-interfaces.adoc, SI-09
- src/docs/specs/spec-acceptance-criteria.adoc, katalog-pflegen.feature

BR-KAT-05 und BR-KAT-06 sind hier bewusst NICHT als Ende-zu-Ende-Szenario
nachgebildet: Sie setzen eine laufende Ausleihe (UC-01, EPIC-A) bzw. eine
abgeschlossene Prüfung (UC-04, EPIC-B) voraus, die erst in späteren EPICs
entstehen. `katalog_service.kategorie_aendern` dokumentiert bereits, warum
für beide Regeln kein zusätzlicher Code in EPIC-D nötig ist.
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient
from hypothesis import given
from hypothesis import strategies as st

from leihgut.adapters.persistence.sqlite_gegenstand_repository import (
    SqliteGegenstandRepository,
    create_connection,
)
from leihgut.adapters.persistence.sqlite_kategorie_repository import (
    SqliteKategorieRepository,
)
from leihgut.adapters.rest.app import create_app
from leihgut.anwendungskern.katalog_service import (
    GegenstandNichtGefunden,
    InventarnummerVergeben,
    KategorieNichtGefunden,
    WertUngueltig,
    _kategorie_werte_pruefen,
    _wiederbeschaffungswert_pruefen,
    gegenstand_anlegen,
    gegenstand_wert_aendern,
    kategorie_aendern,
    kategorie_anlegen,
)
from leihgut.domain.gegenstand import Gegenstand, GegenstandZustand
from leihgut.domain.kategorie import Kategorie
from leihgut.domain.kaution import (
    KAUTION_MAX_CENT,
    KAUTION_MIN_CENT,
    kaution_berechnen,
)


@pytest.fixture
def conn():
    connection = create_connection(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def kategorie_repo(conn):
    return SqliteKategorieRepository(conn)


@pytest.fixture
def gegenstand_repo(conn):
    return SqliteGegenstandRepository(conn)


# --- Unit: Operation-Funktionen, isoliert ohne Port --------------------

class TestKategorieWertePruefen:
    def test_akzeptiert_positive_werte(self):
        assert _kategorie_werte_pruefen(14, 50) is None

    def test_lehnt_leihdauer_null_ab(self):
        fehler = _kategorie_werte_pruefen(0, 50)
        assert fehler == WertUngueltig("leihdauerTage", 0)

    def test_lehnt_negative_leihdauer_ab(self):
        fehler = _kategorie_werte_pruefen(-1, 50)
        assert fehler == WertUngueltig("leihdauerTage", -1)

    def test_lehnt_wartungsintervall_null_ab(self):
        fehler = _kategorie_werte_pruefen(14, 0)
        assert fehler == WertUngueltig("wartungsintervall", 0)


class TestWiederbeschaffungswertPruefen:
    def test_akzeptiert_positiven_wert(self):
        assert _wiederbeschaffungswert_pruefen(8000) is None

    def test_lehnt_null_ab(self):
        assert _wiederbeschaffungswert_pruefen(0) == WertUngueltig(
            "wiederbeschaffungswertCent", 0
        )

    def test_lehnt_negativen_wert_ab(self):
        assert _wiederbeschaffungswert_pruefen(-500) == WertUngueltig(
            "wiederbeschaffungswertCent", -500
        )


# --- Invarianten: Kautionsberechnung (BR-KAT-04) -----------------------

class TestKautionBerechnen:
    @given(st.integers(min_value=1, max_value=10_000_000))
    def test_ergebnis_liegt_immer_im_erlaubten_bereich(self, wert_cent):
        kaution = kaution_berechnen(wert_cent)
        assert KAUTION_MIN_CENT <= kaution <= KAUTION_MAX_CENT

    @given(st.integers(min_value=1, max_value=10_000_000))
    def test_ergebnis_ist_immer_vielfaches_von_100_cent(self, wert_cent):
        kaution = kaution_berechnen(wert_cent)
        assert kaution % 100 == 0

    def test_20_prozent_innerhalb_der_grenzen(self):
        # 8000 ct * 20 % = 1600 ct, liegt zwischen 500 und 10000 ct.
        assert kaution_berechnen(8000) == 1600

    def test_sehr_kleiner_wert_wird_auf_minimum_angehoben(self):
        assert kaution_berechnen(100) == KAUTION_MIN_CENT

    def test_sehr_grosser_wert_wird_auf_maximum_gedeckelt(self):
        assert kaution_berechnen(1_000_000) == KAUTION_MAX_CENT


# --- Service-Ebene: Kategorie ------------------------------------------

class TestKategorieAnlegen:
    def test_legt_kategorie_an(self, kategorie_repo):
        ergebnis = kategorie_anlegen(
            kategorie_repo, "kat-beamer", "Beamer", 7, 100, False
        )

        assert isinstance(ergebnis, Kategorie)
        assert kategorie_repo.find_by_id("kat-beamer") == ergebnis

    def test_lehnt_ungueltige_leihdauer_ab(self, kategorie_repo):
        ergebnis = kategorie_anlegen(
            kategorie_repo, "kat-beamer", "Beamer", 0, 100, False
        )

        assert ergebnis == WertUngueltig("leihdauerTage", 0)
        assert kategorie_repo.find_by_id("kat-beamer") is None


class TestKategorieAendern:
    def test_aendert_bestehende_kategorie(self, kategorie_repo):
        kategorie_anlegen(kategorie_repo, "kat-beamer", "Beamer", 7, 100, False)

        ergebnis = kategorie_aendern(kategorie_repo, "kat-beamer", 14, 100, False)

        assert isinstance(ergebnis, Kategorie)
        assert ergebnis.leihdauer_tage == 14
        assert kategorie_repo.find_by_id("kat-beamer").leihdauer_tage == 14

    def test_lehnt_unbekannte_kategorie_ab(self, kategorie_repo):
        ergebnis = kategorie_aendern(kategorie_repo, "kat-unbekannt", 14, 100, False)

        assert ergebnis == KategorieNichtGefunden("kat-unbekannt")

    def test_lehnt_ungueltiges_wartungsintervall_ab(self, kategorie_repo):
        kategorie_anlegen(kategorie_repo, "kat-beamer", "Beamer", 7, 100, False)

        ergebnis = kategorie_aendern(kategorie_repo, "kat-beamer", 7, 0, False)

        assert ergebnis == WertUngueltig("wartungsintervall", 0)


# --- Service-Ebene: Gegenstand ------------------------------------------

class TestGegenstandAnlegen:
    def test_legt_gegenstand_an(self, gegenstand_repo, kategorie_repo):
        kategorie_anlegen(kategorie_repo, "kat-bohrmaschine", "Bohrmaschine", 14, 50, False)

        ergebnis = gegenstand_anlegen(
            gegenstand_repo, kategorie_repo, "BH-01", "kat-bohrmaschine", 8000
        )

        assert isinstance(ergebnis, Gegenstand)
        assert ergebnis.zustand == GegenstandZustand.VERFUEGBAR
        assert gegenstand_repo.find_by_inventarnummer("BH-01") == ergebnis

    def test_lehnt_bereits_vergebene_inventarnummer_ab(
        self, gegenstand_repo, kategorie_repo
    ):
        # @UC-09 @BR-KAT-01 katalog-pflegen.feature
        kategorie_anlegen(kategorie_repo, "kat-bohrmaschine", "Bohrmaschine", 14, 50, False)
        gegenstand_anlegen(
            gegenstand_repo, kategorie_repo, "BH-01", "kat-bohrmaschine", 8000
        )

        ergebnis = gegenstand_anlegen(
            gegenstand_repo, kategorie_repo, "BH-01", "kat-bohrmaschine", 5000
        )

        assert ergebnis == InventarnummerVergeben("BH-01")

    def test_lehnt_unbekannte_kategorie_ab(self, gegenstand_repo, kategorie_repo):
        ergebnis = gegenstand_anlegen(
            gegenstand_repo, kategorie_repo, "BH-01", "kat-unbekannt", 8000
        )

        assert ergebnis == KategorieNichtGefunden("kat-unbekannt")

    def test_lehnt_ungueltigen_wiederbeschaffungswert_ab(
        self, gegenstand_repo, kategorie_repo
    ):
        kategorie_anlegen(kategorie_repo, "kat-bohrmaschine", "Bohrmaschine", 14, 50, False)

        ergebnis = gegenstand_anlegen(
            gegenstand_repo, kategorie_repo, "BH-01", "kat-bohrmaschine", 0
        )

        assert ergebnis == WertUngueltig("wiederbeschaffungswertCent", 0)


class TestGegenstandWertAendern:
    def test_aendert_wiederbeschaffungswert(self, gegenstand_repo, kategorie_repo):
        kategorie_anlegen(kategorie_repo, "kat-bohrmaschine", "Bohrmaschine", 14, 50, False)
        gegenstand_anlegen(
            gegenstand_repo, kategorie_repo, "BH-01", "kat-bohrmaschine", 8000
        )

        ergebnis = gegenstand_wert_aendern(gegenstand_repo, "BH-01", 9000)

        assert isinstance(ergebnis, Gegenstand)
        assert ergebnis.wiederbeschaffungswert_cent == 9000
        assert (
            gegenstand_repo.find_by_inventarnummer("BH-01").wiederbeschaffungswert_cent
            == 9000
        )

    def test_lehnt_unbekannten_gegenstand_ab(self, gegenstand_repo):
        ergebnis = gegenstand_wert_aendern(gegenstand_repo, "UNBEKANNT", 9000)

        assert ergebnis == GegenstandNichtGefunden("UNBEKANNT")

    def test_lehnt_ungueltigen_wert_ab(self, gegenstand_repo, kategorie_repo):
        kategorie_anlegen(kategorie_repo, "kat-bohrmaschine", "Bohrmaschine", 14, 50, False)
        gegenstand_anlegen(
            gegenstand_repo, kategorie_repo, "BH-01", "kat-bohrmaschine", 8000
        )

        ergebnis = gegenstand_wert_aendern(gegenstand_repo, "BH-01", -1)

        assert ergebnis == WertUngueltig("wiederbeschaffungswertCent", -1)


# --- Akzeptanz-Ebene: REST (SI-09) --------------------------------------

class TestKatalogRest:
    def test_post_kategorien_gibt_201_zurueck(self, conn):
        client = TestClient(create_app(conn))

        response = client.post(
            "/kategorien",
            headers={"X-Rolle": "wart"},
            json={
                "kategorieId": "kat-beamer",
                "name": "Beamer",
                "leihdauerTage": 7,
                "wartungsintervall": 100,
                "einweisungspflichtig": False,
            },
        )

        assert response.status_code == 201
        assert response.json()["kategorieId"] == "kat-beamer"

    def test_post_kategorien_ohne_rolle_wird_abgelehnt(self, conn):
        client = TestClient(create_app(conn))

        response = client.post(
            "/kategorien",
            headers={"X-Rolle": "mitglied"},
            json={
                "kategorieId": "kat-beamer",
                "name": "Beamer",
                "leihdauerTage": 7,
                "wartungsintervall": 100,
                "einweisungspflichtig": False,
            },
        )

        assert response.status_code == 403
        assert response.json()["detail"]["fehlercode"] == "ROLLE_NICHT_BERECHTIGT"

    def test_post_gegenstaende_lehnt_vergebene_inventarnummer_mit_409_ab(self, conn):
        # @UC-09 @BR-KAT-01 katalog-pflegen.feature
        client = TestClient(create_app(conn))
        client.post(
            "/kategorien",
            headers={"X-Rolle": "wart"},
            json={
                "kategorieId": "kat-bohrmaschine",
                "name": "Bohrmaschine",
                "leihdauerTage": 14,
                "wartungsintervall": 50,
                "einweisungspflichtig": False,
            },
        )
        client.post(
            "/gegenstaende",
            headers={"X-Rolle": "wart"},
            json={
                "inventarnummer": "BH-01",
                "kategorieId": "kat-bohrmaschine",
                "wiederbeschaffungswertCent": 8000,
            },
        )

        response = client.post(
            "/gegenstaende",
            headers={"X-Rolle": "wart"},
            json={
                "inventarnummer": "BH-01",
                "kategorieId": "kat-bohrmaschine",
                "wiederbeschaffungswertCent": 5000,
            },
        )

        assert response.status_code == 409
        assert response.json()["detail"]["fehlercode"] == "INVENTARNUMMER_VERGEBEN"
