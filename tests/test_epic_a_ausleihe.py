"""EPIC-A: Ausleihe-Kernprozess (UC-01/UC-03).

Referenzen:
- src/docs/implementation/epic-a-ausleihe-kernprozess.adoc
- src/docs/specs/spec-use-cases.adoc, UC-01, UC-03
- src/docs/specs/spec-system-interfaces.adoc, SI-01, SI-03
- src/docs/specs/spec-acceptance-criteria.adoc,
  gegenstand-ausgeben.feature, gegenstand-zuruecknehmen.feature
- ADR-007 (transaktionale Exklusivität bei der Ausgabe)
"""
import sqlite3
import threading

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
from leihgut.adapters.persistence.sqlite_vormerkung_repository import (
    SqliteVormerkungRepository,
)
from leihgut.adapters.rest.app import create_app
from leihgut.anwendungskern.ausleihe_service import (
    AusleiheNichtGefunden,
    AusleihlimitErreicht,
    BereitsZurueckgegeben,
    EinweisungFehlt,
    GegenstandNichtGefunden,
    GegenstandNichtVerfuegbar,
    MitgliedGesperrt,
    _ausgabe_pruefen,
    gegenstand_ausgeben,
    gegenstand_zuruecknehmen,
)
from leihgut.domain.ausleihe import Ausleihe, AusleiheZustand
from leihgut.domain.gegenstand import Gegenstand, GegenstandZustand
from leihgut.domain.kategorie import Kategorie
from tests.fakes import FakeClock


@pytest.fixture
def conn():
    connection = create_connection(":memory:")
    connection.execute(
        "INSERT INTO kategorie "
        "(kategorie_id, name, leihdauer_tage, wartungsintervall, einweisungspflichtig) "
        "VALUES (?, ?, ?, ?, ?)",
        ("kat-nagelmesser", "Nagelmesser", 14, 20, 0),
    )
    connection.execute(
        "INSERT INTO kategorie "
        "(kategorie_id, name, leihdauer_tage, wartungsintervall, einweisungspflichtig) "
        "VALUES (?, ?, ?, ?, ?)",
        ("kat-kettensaege", "Kettensaege", 7, 20, 1),
    )
    connection.commit()
    yield connection
    connection.close()


def _gegenstand_anlegen(conn, inventarnummer, kategorie_id, wbw, zustand="verfuegbar"):
    conn.execute(
        "INSERT INTO gegenstand "
        "(inventarnummer, kategorie_id, wiederbeschaffungswert_cent, "
        "nutzungszaehler, zustand) VALUES (?, ?, ?, 0, ?)",
        (inventarnummer, kategorie_id, wbw, zustand),
    )
    conn.commit()


def _ausleihe_anlegen(
    conn, ausleihe_id, gegenstand_id, mitglied_id, ausgabedatum, rueckgabefrist,
    kaution_cent=2000, zustand="aktiv",
):
    conn.execute(
        "INSERT INTO ausleihe "
        "(ausleihe_id, gegenstand_id, mitglied_id, ausgabedatum, "
        "rueckgabefrist, kaution_cent, verlaengert, zustand) "
        "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
        (ausleihe_id, gegenstand_id, mitglied_id, ausgabedatum, rueckgabefrist,
         kaution_cent, zustand),
    )
    conn.commit()


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
def ausleihe_repo(conn):
    return SqliteAusleiheRepository(conn)


@pytest.fixture
def vormerkung_repo(conn):
    return SqliteVormerkungRepository(conn)


@pytest.fixture
def clock():
    return FakeClock("2026-08-18T10:00:00")


# --- Operation: _ausgabe_pruefen isoliert (IOSP) -------------------------

class TestAusgabePruefen:
    def _kategorie(self, einweisungspflichtig=False):
        return Kategorie(
            kategorie_id="kat-1",
            name="Test",
            leihdauer_tage=14,
            wartungsintervall=20,
            einweisungspflichtig=einweisungspflichtig,
        )

    def _gegenstand(self, zustand=GegenstandZustand.VERFUEGBAR):
        return Gegenstand(
            inventarnummer="INV-1",
            kategorie_id="kat-1",
            zustand=zustand,
            wiederbeschaffungswert_cent=10000,
        )

    def test_erlaubt_wenn_alle_bedingungen_erfuellt(self):
        # @UC-01 @BR-AUS-01 gegenstand-ausgeben.feature
        ergebnis = _ausgabe_pruefen(
            self._gegenstand(), self._kategorie(), "M-1", False, 0, True
        )
        assert ergebnis is None

    def test_lehnt_nicht_verfuegbaren_gegenstand_ab(self):
        # @UC-01 @BR-AUS-01 gegenstand-ausgeben.feature
        ergebnis = _ausgabe_pruefen(
            self._gegenstand(GegenstandZustand.AUSGELIEHEN),
            self._kategorie(), "M-1", False, 0, True,
        )
        assert ergebnis == GegenstandNichtVerfuegbar("INV-1")

    def test_lehnt_gesperrtes_mitglied_ab(self):
        # @UC-01 @BR-AUS-03 gegenstand-ausgeben.feature
        ergebnis = _ausgabe_pruefen(
            self._gegenstand(), self._kategorie(), "M-2", True, 0, True
        )
        assert ergebnis == MitgliedGesperrt("M-2")

    def test_lehnt_bei_ausleihlimit_ab(self):
        # @UC-01 @BR-AUS-02 gegenstand-ausgeben.feature
        ergebnis = _ausgabe_pruefen(
            self._gegenstand(), self._kategorie(), "M-3", False, 3, True
        )
        assert ergebnis == AusleihlimitErreicht("M-3")

    def test_lehnt_fehlende_einweisung_ab(self):
        # @UC-01 @BR-AUS-04 gegenstand-ausgeben.feature
        ergebnis = _ausgabe_pruefen(
            self._gegenstand(), self._kategorie(einweisungspflichtig=True),
            "M-5", False, 0, False,
        )
        assert ergebnis == EinweisungFehlt("M-5", "kat-1")

    def test_prueft_in_spezifizierter_reihenfolge(self):
        """Verfügbarkeit vor Sperre vor Limit vor Einweisung (SI-01)."""
        ergebnis = _ausgabe_pruefen(
            self._gegenstand(GegenstandZustand.AUSGELIEHEN),
            self._kategorie(einweisungspflichtig=True),
            "M-9", True, 5, False,
        )
        assert ergebnis == GegenstandNichtVerfuegbar("INV-1")


# --- Integration: gegenstand_ausgeben (UC-01) ---------------------------

class TestGegenstandAusgeben:
    def test_gibt_verfuegbaren_gegenstand_aus(
        self, conn, gegenstand_repo, kategorie_repo, einweisung_repo,
        ausleihe_repo, clock,
    ):
        # @UC-01 @BR-AUS-01 gegenstand-ausgeben.feature:
        # "Ausgabe eines verfügbaren Gegenstands"
        _gegenstand_anlegen(conn, "BH-01", "kat-nagelmesser", 10000)

        ergebnis = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo,
            clock, "BH-01", "M-1",
        )

        assert isinstance(ergebnis, Ausleihe)
        assert ergebnis.zustand == AusleiheZustand.AKTIV
        assert ergebnis.ausgabedatum == "2026-08-18"
        assert ergebnis.rueckgabefrist == "2026-09-01"  # +14 Tage
        assert ergebnis.kaution_cent == 2000  # 20% von 10000
        assert ergebnis.verlaengert is False
        aktualisiert = gegenstand_repo.find_by_inventarnummer("BH-01")
        assert aktualisiert.zustand == GegenstandZustand.AUSGELIEHEN

    def test_lehnt_nicht_gefundenen_gegenstand_ab(
        self, gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo, clock,
    ):
        ergebnis = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo,
            clock, "UNBEKANNT", "M-1",
        )
        assert ergebnis == GegenstandNichtGefunden("UNBEKANNT")

    def test_lehnt_ausgeliehenen_gegenstand_ab(
        self, conn, gegenstand_repo, kategorie_repo, einweisung_repo,
        ausleihe_repo, clock,
    ):
        # @UC-01 @BR-AUS-01 gegenstand-ausgeben.feature:
        # "Ausgabe eines ausgeliehenen Gegenstands wird abgelehnt"
        _gegenstand_anlegen(
            conn, "BH-01", "kat-nagelmesser", 10000, zustand="ausgeliehen"
        )

        ergebnis = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo,
            clock, "BH-01", "M-1",
        )

        assert ergebnis == GegenstandNichtVerfuegbar("BH-01")

    def test_lehnt_ausgabe_an_gesperrtes_mitglied_ab(
        self, conn, gegenstand_repo, kategorie_repo, einweisung_repo,
        ausleihe_repo, clock,
    ):
        # @UC-01 @BR-AUS-03 gegenstand-ausgeben.feature:
        # "Ausgabe an gesperrtes Mitglied wird abgelehnt"
        _gegenstand_anlegen(conn, "BH-01", "kat-nagelmesser", 10000)
        _gegenstand_anlegen(
            conn, "BH-02", "kat-nagelmesser", 10000, zustand="ausgeliehen"
        )
        _ausleihe_anlegen(
            conn, "A-1", "BH-02", "M-2", "2026-08-01", "2026-08-10",
        )  # überfällig (Frist < heute)

        ergebnis = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo,
            clock, "BH-01", "M-2",
        )

        assert ergebnis == MitgliedGesperrt("M-2")

    def test_lehnt_viertes_gleichzeitiges_ausleihen_ab(
        self, conn, gegenstand_repo, kategorie_repo, einweisung_repo,
        ausleihe_repo, clock,
    ):
        # @UC-01 @BR-AUS-02 gegenstand-ausgeben.feature:
        # "Viertes gleichzeitiges Ausleihen wird abgelehnt"
        for i in range(3):
            _gegenstand_anlegen(
                conn, f"BH-0{i}", "kat-nagelmesser", 10000, zustand="ausgeliehen"
            )
            _ausleihe_anlegen(
                conn, f"A-{i}", f"BH-0{i}", "M-3", "2026-08-18", "2026-09-01",
            )
        _gegenstand_anlegen(conn, "KS-01", "kat-nagelmesser", 10000)

        ergebnis = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo,
            clock, "KS-01", "M-3",
        )

        assert ergebnis == AusleihlimitErreicht("M-3")

    def test_zurueckgegebene_ungeprueft_ausleihe_zaehlt_gegen_limit(
        self, conn, gegenstand_repo, kategorie_repo, einweisung_repo,
        ausleihe_repo, clock,
    ):
        # @UC-01 @BR-AUS-02 gegenstand-ausgeben.feature:
        # "Zurückgegebene, aber ungeprüfte Ausleihe zählt gegen das Limit"
        for i in range(2):
            _gegenstand_anlegen(
                conn, f"BH-0{i}", "kat-nagelmesser", 10000, zustand="ausgeliehen"
            )
            _ausleihe_anlegen(
                conn, f"A-{i}", f"BH-0{i}", "M-4", "2026-08-18", "2026-09-01",
            )
        _gegenstand_anlegen(
            conn, "BH-09", "kat-nagelmesser", 10000, zustand="in_pruefung"
        )
        _ausleihe_anlegen(
            conn, "A-9", "BH-09", "M-4", "2026-08-10", "2026-08-24",
            zustand="zurueckgegeben",
        )
        _gegenstand_anlegen(conn, "KS-02", "kat-nagelmesser", 10000)

        ergebnis = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo,
            clock, "KS-02", "M-4",
        )

        assert ergebnis == AusleihlimitErreicht("M-4")

    def test_lehnt_einweisungspflichtigen_gegenstand_ohne_einweisung_ab(
        self, conn, gegenstand_repo, kategorie_repo, einweisung_repo,
        ausleihe_repo, clock,
    ):
        # @UC-01 @BR-AUS-04 gegenstand-ausgeben.feature:
        # "Einweisungspflichtiger Gegenstand ohne Einweisung wird abgelehnt"
        _gegenstand_anlegen(conn, "KS-03", "kat-kettensaege", 60000)

        ergebnis = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo,
            clock, "KS-03", "M-5",
        )

        assert ergebnis == EinweisungFehlt("M-5", "kat-kettensaege")

    @pytest.mark.parametrize(
        "wbw,kaution_erwartet",
        [(10000, 2000), (1000, 500), (60000, 10000), (2000, 500)],
    )
    def test_kautionsberechnung_bei_ausgabe(
        self, conn, gegenstand_repo, kategorie_repo, einweisung_repo,
        ausleihe_repo, clock, wbw, kaution_erwartet,
    ):
        # @UC-01 @BR-AUS-05 @BR-KAT-04 gegenstand-ausgeben.feature:
        # "Kautionsberechnung bei Ausgabe" (Scenario Outline)
        inventarnummer = f"WBW-{wbw}"
        _gegenstand_anlegen(conn, inventarnummer, "kat-nagelmesser", wbw)

        ergebnis = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo, ausleihe_repo,
            clock, inventarnummer, "M-6",
        )

        assert isinstance(ergebnis, Ausleihe)
        assert ergebnis.kaution_cent == kaution_erwartet


# --- Integration: gegenstand_zuruecknehmen (UC-03) -----------------------

class TestGegenstandZuruecknehmen:
    def test_versetzt_gegenstand_in_pruefung_ohne_ausleihe_abzuschliessen(
        self, conn, gegenstand_repo, ausleihe_repo, vormerkung_repo,
    ):
        # @UC-03 @BR-RUP-01 gegenstand-zuruecknehmen.feature:
        # "Rückgabe versetzt Gegenstand in Prüfung, ohne die Ausleihe abzuschließen"
        _gegenstand_anlegen(conn, "NM-01", "kat-nagelmesser", 10000, "ausgeliehen")
        _ausleihe_anlegen(conn, "A-8", "NM-01", "M-1", "2026-08-18", "2026-09-01")

        ergebnis = gegenstand_zuruecknehmen(ausleihe_repo, gegenstand_repo, vormerkung_repo, "A-8")

        assert isinstance(ergebnis, Ausleihe)
        assert ergebnis.zustand == AusleiheZustand.ZURUECKGEGEBEN
        gegenstand = gegenstand_repo.find_by_inventarnummer("NM-01")
        assert gegenstand.zustand == GegenstandZustand.IN_PRUEFUNG

    def test_erfasst_auffaelligkeiten_als_freitext(
        self, conn, gegenstand_repo, ausleihe_repo, vormerkung_repo,
    ):
        # @UC-03 @BR-RUP-02 gegenstand-zuruecknehmen.feature:
        # "Auffälligkeiten werden als Freitext erfasst, ohne den
        # Kautionsabzug festzulegen"
        _gegenstand_anlegen(conn, "NM-02", "kat-nagelmesser", 10000, "ausgeliehen")
        _ausleihe_anlegen(conn, "A-9", "NM-02", "M-1", "2026-08-18", "2026-09-01")

        ergebnis = gegenstand_zuruecknehmen(
            ausleihe_repo, gegenstand_repo, vormerkung_repo, "A-9", "Riss im Gehäuse"
        )

        assert ergebnis.rueckgabe_auffaelligkeiten == "Riss im Gehäuse"
        assert ergebnis.kaution_cent == 2000  # unverändert, kein Abzug hier

    def test_lehnt_nicht_gefundene_ausleihe_ab(self, gegenstand_repo, ausleihe_repo, vormerkung_repo):
        ergebnis = gegenstand_zuruecknehmen(ausleihe_repo, gegenstand_repo, vormerkung_repo, "X")
        assert ergebnis == AusleiheNichtGefunden("X")

    def test_lehnt_erneute_rueckgabe_ab(self, conn, gegenstand_repo, ausleihe_repo, vormerkung_repo):
        # @UC-03 gegenstand-zuruecknehmen.feature:
        # "Erneute Rückgabe einer bereits zurückgegebenen Ausleihe wird abgelehnt"
        _gegenstand_anlegen(conn, "NM-03", "kat-nagelmesser", 10000, "in_pruefung")
        _ausleihe_anlegen(
            conn, "A-10", "NM-03", "M-1", "2026-08-01", "2026-08-15",
            zustand="zurueckgegeben",
        )

        ergebnis = gegenstand_zuruecknehmen(ausleihe_repo, gegenstand_repo, vormerkung_repo, "A-10")

        assert ergebnis == BereitsZurueckgegeben("A-10")


# --- DB-Schranke: korrigierte zustand-CHECK-Constraint -------------------

class TestAusleiheZustandCheck:
    """Beweis, dass die in dieser Story korrigierte CHECK-Constraint
    (schema.sql) tatsächlich nur die vier Ausleihe-Zustände zulässt."""

    def test_ungueltiger_zustand_wird_von_db_abgelehnt(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ausleihe "
                "(ausleihe_id, gegenstand_id, mitglied_id, ausgabedatum, "
                "rueckgabefrist, kaution_cent, verlaengert, zustand) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("A-X", "G-X", "M-X", "2026-08-18", "2026-09-01", 2000, 0,
                 "in_pruefung"),  # Gegenstand-Zustand, kein Ausleihe-Zustand
            )


# --- ADR-007: Repository und Service übersetzen IntegrityError ----------

class TestAusleiheRepositoryNebenlaeufigkeit:
    """Direkter (nicht nebenläufiger) Test: `insert()` übersetzt den vom
    partiellen Unique-Index ausgelösten `sqlite3.IntegrityError` in
    `NebenlaeufigeAusgabeAbgelehnt` (ADR-007)."""

    def test_zweite_aktive_ausleihe_desselben_gegenstands_wird_abgelehnt(
        self, conn, ausleihe_repo, gegenstand_repo,
    ):
        from leihgut.ports.ausleihe_repository import NebenlaeufigeAusgabeAbgelehnt

        _gegenstand_anlegen(conn, "BH-20", "kat-nagelmesser", 10000, "ausgeliehen")
        ausleihe_repo.insert(
            Ausleihe(
                ausleihe_id="A-30",
                gegenstand_id="BH-20",
                mitglied_id="M-1",
                ausgabedatum="2026-08-18",
                rueckgabefrist="2026-09-01",
                kaution_cent=2000,
            )
        )

        with pytest.raises(NebenlaeufigeAusgabeAbgelehnt):
            ausleihe_repo.insert(
                Ausleihe(
                    ausleihe_id="A-31",
                    gegenstand_id="BH-20",
                    mitglied_id="M-2",
                    ausgabedatum="2026-08-18",
                    rueckgabefrist="2026-09-01",
                    kaution_cent=2000,
                )
            )


class TestGegenstandAusgebenUebersetztNebenlaeufigkeit:
    """Der Anwendungsdienst fängt `NebenlaeufigeAusgabeAbgelehnt` ab und
    liefert `GegenstandNichtVerfuegbar` statt die Ausnahme durchzureichen
    (ADR-007)."""

    class _RepoDerImmerAbgelehntWird:
        def finde_offene_fuer_mitglied(self, mitglied_id):
            return []

        def insert(self, ausleihe):
            from leihgut.ports.ausleihe_repository import (
                NebenlaeufigeAusgabeAbgelehnt,
            )

            raise NebenlaeufigeAusgabeAbgelehnt(ausleihe.gegenstand_id)

    def test_liefert_gegenstand_nicht_verfuegbar(
        self, conn, gegenstand_repo, kategorie_repo, einweisung_repo, clock,
    ):
        _gegenstand_anlegen(conn, "BH-21", "kat-nagelmesser", 10000)

        ergebnis = gegenstand_ausgeben(
            gegenstand_repo, kategorie_repo, einweisung_repo,
            self._RepoDerImmerAbgelehntWird(), clock, "BH-21", "M-1",
        )

        assert ergebnis == GegenstandNichtVerfuegbar("BH-21")


# --- REST-Ebene (SI-01/SI-03) --------------------------------------------

@pytest.fixture
def client_und_conn(tmp_path):
    connection = create_connection(":memory:")
    connection.execute(
        "INSERT INTO kategorie "
        "(kategorie_id, name, leihdauer_tage, wartungsintervall, einweisungspflichtig) "
        "VALUES (?, ?, ?, ?, ?)",
        ("kat-nagelmesser", "Nagelmesser", 14, 20, 0),
    )
    connection.commit()
    from fastapi.testclient import TestClient

    app = create_app(connection, clock=FakeClock("2026-08-18T10:00:00"))
    client = TestClient(app)
    yield client, connection
    connection.close()


class TestRestAusgabeUndRueckgabe:
    def test_post_ausgabe_erfolgreich(self, client_und_conn):
        client, conn = client_und_conn
        _gegenstand_anlegen(conn, "BH-10", "kat-nagelmesser", 10000)

        antwort = client.post(
            "/gegenstaende/BH-10/ausgabe",
            json={"mitgliedId": "M-1"},
            headers={"X-Rolle": "thekendienst"},
        )

        assert antwort.status_code == 201
        koerper = antwort.json()
        assert koerper["gegenstandId"] == "BH-10"
        assert koerper["kautionCent"] == 2000
        assert koerper["zustand"] == "aktiv"

    def test_post_ausgabe_lehnt_nicht_gefunden_ab(self, client_und_conn):
        client, _ = client_und_conn
        antwort = client.post(
            "/gegenstaende/UNBEKANNT/ausgabe",
            json={"mitgliedId": "M-1"},
            headers={"X-Rolle": "thekendienst"},
        )
        assert antwort.status_code == 404
        assert antwort.json()["detail"]["fehlercode"] == "GEGENSTAND_NICHT_GEFUNDEN"

    def test_post_ausgabe_verlangt_thekendienst_rolle(self, client_und_conn):
        client, conn = client_und_conn
        _gegenstand_anlegen(conn, "BH-11", "kat-nagelmesser", 10000)

        antwort = client.post(
            "/gegenstaende/BH-11/ausgabe",
            json={"mitgliedId": "M-1"},
            headers={"X-Rolle": "mitglied"},
        )
        assert antwort.status_code == 403

    def test_post_rueckgabe_erfolgreich(self, client_und_conn):
        client, conn = client_und_conn
        _gegenstand_anlegen(conn, "BH-12", "kat-nagelmesser", 10000, "ausgeliehen")
        _ausleihe_anlegen(conn, "A-20", "BH-12", "M-1", "2026-08-18", "2026-09-01")

        antwort = client.post(
            "/ausleihen/A-20/rueckgabe",
            json={"auffaelligkeiten": "Riss"},
            headers={"X-Rolle": "thekendienst"},
        )

        assert antwort.status_code == 200
        koerper = antwort.json()
        assert koerper["zustand"] == "zurueckgegeben"

    def test_post_rueckgabe_lehnt_bereits_zurueckgegebene_ab(self, client_und_conn):
        client, conn = client_und_conn
        _gegenstand_anlegen(conn, "BH-13", "kat-nagelmesser", 10000, "in_pruefung")
        _ausleihe_anlegen(
            conn, "A-21", "BH-13", "M-1", "2026-08-01", "2026-08-15",
            zustand="zurueckgegeben",
        )

        antwort = client.post(
            "/ausleihen/A-21/rueckgabe",
            json={},
            headers={"X-Rolle": "thekendienst"},
        )

        assert antwort.status_code == 409
        assert antwort.json()["detail"]["fehlercode"] == "BEREITS_ZURUECKGEGEBEN"


# --- ADR-007: Nebenläufigkeitstest gegen echte SQLite-Datei --------------

class TestNebenlaeufigeAusgabe:
    """ADR-007: zwei Threads gegen dieselbe echte SQLite-Datei (nicht
    ``:memory:``) rufen praktisch gleichzeitig `gegenstand_ausgeben` für
    denselben Gegenstand auf. Erwartet wird genau ein Erfolg und eine
    Ablehnung mit `GEGENSTAND_NICHT_VERFUEGBAR`, kein unbehandelter
    `sqlite3.IntegrityError` (siehe Analyse in
    epic-a-ausleihe-kernprozess.adoc, User Story A1)."""

    def test_genau_eine_ausgabe_gewinnt(self, tmp_path):
        db_pfad = str(tmp_path / "leihgut-test.db")
        setup_conn = create_connection(db_pfad)
        setup_conn.execute(
            "INSERT INTO kategorie "
            "(kategorie_id, name, leihdauer_tage, wartungsintervall, "
            "einweisungspflichtig) VALUES (?, ?, ?, ?, ?)",
            ("kat-nagelmesser", "Nagelmesser", 14, 20, 0),
        )
        setup_conn.execute(
            "INSERT INTO gegenstand "
            "(inventarnummer, kategorie_id, wiederbeschaffungswert_cent, "
            "nutzungszaehler, zustand) VALUES (?, ?, ?, 0, 'verfuegbar')",
            ("RACE-01", "kat-nagelmesser", 10000),
        )
        setup_conn.commit()
        setup_conn.close()

        ergebnisse = [None, None]
        barriere = threading.Barrier(2)

        def ausgeben(index, mitglied_id):
            conn = sqlite3.connect(db_pfad, check_same_thread=False, timeout=5)
            conn.execute("PRAGMA foreign_keys = ON")
            gegenstand_repo = SqliteGegenstandRepository(conn)
            kategorie_repo = SqliteKategorieRepository(conn)
            einweisung_repo = SqliteEinweisungRepository(conn)
            ausleihe_repo = SqliteAusleiheRepository(conn)
            clock = FakeClock("2026-08-18T10:00:00")
            barriere.wait()
            ergebnisse[index] = gegenstand_ausgeben(
                gegenstand_repo, kategorie_repo, einweisung_repo,
                ausleihe_repo, clock, "RACE-01", mitglied_id,
            )
            conn.close()

        threads = [
            threading.Thread(target=ausgeben, args=(0, "M-A")),
            threading.Thread(target=ausgeben, args=(1, "M-B")),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        erfolge = [e for e in ergebnisse if isinstance(e, Ausleihe)]
        ablehnungen = [e for e in ergebnisse if isinstance(e, GegenstandNichtVerfuegbar)]
        assert len(erfolge) == 1
        assert len(ablehnungen) == 1
