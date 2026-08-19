"""Tests für EPIC-B (Prüfung & Kaution, UC-04 / SI-04).

Umfasst: BR-RUP-04 (Ausleihe abschließen), BR-RUP-05 (Mängel-Duplikate),
BR-KAU-01/02/04 (Kautionsbewegungen), BR-WAR-01/02 (Nutzungszähler &
Wartungsfrist), SI-04 Validierung & REST-Endpoint.
"""
import sqlite3
from datetime import datetime

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
from leihgut.adapters.persistence.sqlite_maengel_repository import (
    SqliteMaengelRepository,
)
from leihgut.adapters.persistence.sqlite_pruefabschluss_repository import (
    SqlitePruefabschlussRepository,
)
from leihgut.adapters.rest.app import create_app
from leihgut.anwendungskern.pruefung_service import (
    AbzugUebersteigtKaution,
    AusleiheNichtGefunden,
    NichtInPruefung,
    pruefung_abschliessen,
)
from leihgut.domain.ausleihe import Ausleihe, AusleiheZustand
from leihgut.domain.gegenstand import Gegenstand, GegenstandZustand
from leihgut.domain.kategorie import Kategorie
from tests.fakes import FakeClock


def create_connection_with_data():
    """Erstellt eine Testdatenbank mit Testdaten (eine Kategorie, ein
    Gegenstand in Prüfung, eine Ausleihe im Zustand Zurückgegeben)."""
    conn = create_connection(":memory:")
    conn.row_factory = sqlite3.Row  # Dictionaries statt Tuples

    kategorie_id = "cat-1"
    inventarnummer = "inv-1"
    ausleihe_id = "lease-1"
    mitglied_id = "member-1"

    conn.execute(
        """
        INSERT INTO kategorie (kategorie_id, name, leihdauer_tage,
                              wartungsintervall, einweisungspflichtig)
        VALUES (?, ?, ?, ?, ?)
        """,
        (kategorie_id, "Werkzeug", 14, 20, False),
    )

    conn.execute(
        """
        INSERT INTO gegenstand (inventarnummer, kategorie_id, zustand,
                               wiederbeschaffungswert_cent, nutzungszaehler)
        VALUES (?, ?, ?, ?, ?)
        """,
        (inventarnummer, kategorie_id, "in_pruefung", 5000, 5),
    )

    ausgabedatum = "2025-01-15"
    rueckgabefrist = "2025-01-29"

    conn.execute(
        """
        INSERT INTO ausleihe (ausleihe_id, gegenstand_id, mitglied_id,
                             ausgabedatum, rueckgabefrist, kaution_cent,
                             verlaengert, zustand, rueckgabe_auffaelligkeiten)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ausleihe_id,
            inventarnummer,
            mitglied_id,
            ausgabedatum,
            rueckgabefrist,
            2000,
            False,
            "zurueckgegeben",
            None,
        ),
    )

    conn.commit()
    return conn, kategorie_id, inventarnummer, ausleihe_id


@pytest.fixture
def conn():
    """SQLite-Testdatenbank mit Testdaten."""
    c, _, _, _ = create_connection_with_data()
    yield c
    c.close()


@pytest.fixture
def conn_with_ids(conn):
    """Konvenienzfixture gibt Datenbankverbindung und Test-IDs zurück."""
    c, cat_id, inv, lease_id = create_connection_with_data()
    yield c, cat_id, inv, lease_id
    c.close()


@pytest.fixture
def clock():
    """FakeClock für konsistente Zeitstempel in Tests."""
    return FakeClock(datetime(2025, 1, 30, 14, 30, 0))


@pytest.fixture
def repos(conn, clock):
    """Repositories für die Testdatenbank."""
    return {
        "gegenstand": SqliteGegenstandRepository(conn),
        "kategorie": SqliteKategorieRepository(conn),
        "ausleihe": SqliteAusleiheRepository(conn),
        "maengel": SqliteMaengelRepository(conn),
        "pruefabschluss": SqlitePruefabschlussRepository(conn),
    }


# --- Unit Tests für reine Operation _pruefung_pruefen ---------------

class TestPruefungValidierung:
    """Validates `_pruefung_pruefen` Operation (keine Ports)."""

    def test_nicht_in_pruefung_ablehnung(self):
        """Wenn Gegenstand nicht in_pruefung ist, Ablehnung."""
        from leihgut.anwendungskern.pruefung_service import _pruefung_pruefen

        ablehnung = _pruefung_pruefen(
            "lease-1",
            GegenstandZustand.VERFUEGBAR,  # nicht in_pruefung
            2000,
            500,
        )
        assert isinstance(ablehnung, NichtInPruefung)
        assert ablehnung.ausleihe_id == "lease-1"

    def test_abzug_uebersteigt_kaution_ablehnung(self):
        """Wenn Abzug > Kaution (BR-KAU-02), Ablehnung."""
        from leihgut.anwendungskern.pruefung_service import _pruefung_pruefen

        ablehnung = _pruefung_pruefen(
            "lease-1",
            GegenstandZustand.IN_PRUEFUNG,
            2000,
            2500,  # abzug > kaution
        )
        assert isinstance(ablehnung, AbzugUebersteigtKaution)
        assert ablehnung.kautionsabzug_cent == 2500
        assert ablehnung.hinterlegte_kaution_cent == 2000

    def test_validierung_erfolgreich(self):
        """Bei gültigen Eingaben: None (kein Fehler)."""
        from leihgut.anwendungskern.pruefung_service import _pruefung_pruefen

        result = _pruefung_pruefen(
            "lease-1", GegenstandZustand.IN_PRUEFUNG, 2000, 500
        )
        assert result is None


# --- Integration-Tests: Service-Aufrufe gegen echte SQLite ------

class TestPruefungAbschliessen:
    """Integration tests für `pruefung_abschliessen` Service."""

    def test_erfolgreiche_pruefung_abschliessen(self, repos, clock):
        """Happy Path: Prüfung abgeschlossen, Ausleihe ABGESCHLOSSEN,
        Gegenstand VERFUEGBAR, Kautionsbewegungen eingefügt."""
        ergebnis = pruefung_abschliessen(
            repos["ausleihe"],
            repos["gegenstand"],
            repos["kategorie"],
            repos["maengel"],
            repos["pruefabschluss"],
            clock,
            "lease-1",
            ["Kratzer am Griff"],
            500,
            "verfuegbar",
        )

        assert ergebnis is not None
        assert hasattr(ergebnis, "pruefprotokoll_id")
        assert ergebnis.kautionsabzug_cent == 500
        assert ergebnis.neuer_gegenstand_zustand == GegenstandZustand.VERFUEGBAR

        # BR-RUP-04: Ausleihe in ABGESCHLOSSEN überführt
        ausleihe = repos["ausleihe"].find_by_id("lease-1")
        assert ausleihe.zustand == AusleiheZustand.ABGESCHLOSSEN

        # Gegenstand aktualisiert: nutzungszaehler+1 (BR-WAR-01), Zustand
        gegenstand = repos["gegenstand"].find_by_inventarnummer("inv-1")
        assert gegenstand.zustand == GegenstandZustand.VERFUEGBAR
        assert gegenstand.nutzungszaehler == 6  # war 5, +1

    def test_ausleihe_nicht_gefunden(self, repos, clock):
        """Wenn Ausleihe nicht existiert: 404."""
        ergebnis = pruefung_abschliessen(
            repos["ausleihe"],
            repos["gegenstand"],
            repos["kategorie"],
            repos["maengel"],
            repos["pruefabschluss"],
            clock,
            "nonexistent-lease",
            [],
            500,
            "verfuegbar",
        )
        assert isinstance(ergebnis, AusleiheNichtGefunden)

    def test_gegenstand_nicht_in_pruefung(self, conn, repos, clock):
        """Wenn Gegenstand nicht in_pruefung: 409 NICHT_IN_PRUEFUNG."""
        conn.execute(
            "UPDATE gegenstand SET zustand = ? WHERE inventarnummer = ?",
            ("verfuegbar", "inv-1"),
        )
        conn.commit()

        ergebnis = pruefung_abschliessen(
            repos["ausleihe"],
            repos["gegenstand"],
            repos["kategorie"],
            repos["maengel"],
            repos["pruefabschluss"],
            clock,
            "lease-1",
            [],
            500,
            "verfuegbar",
        )
        assert isinstance(ergebnis, NichtInPruefung)

    def test_abzug_uebersteigt_kaution(self, repos, clock):
        """Wenn Abzug > Kaution (BR-KAU-02): 422."""
        ergebnis = pruefung_abschliessen(
            repos["ausleihe"],
            repos["gegenstand"],
            repos["kategorie"],
            repos["maengel"],
            repos["pruefabschluss"],
            clock,
            "lease-1",
            [],
            2500,  # kaution ist 2000
            "verfuegbar",
        )
        assert isinstance(ergebnis, AbzugUebersteigtKaution)
        assert ergebnis.kautionsabzug_cent == 2500

    def test_bru_war02_wartungsfaellig_transition(self, conn, repos, clock):
        """BR-WAR-02: Wenn nutzungszaehler+1 >= wartungsintervall,
        Gegenstand wird WARTUNGSFAELLIG (nicht VERFUEGBAR)."""
        # Gegenstand hat nutzungszaehler=5, wartungsintervall=20
        # Nach +1: 6 < 20 -> immer noch VERFUEGBAR
        # Setze nutzungszaehler=19 damit nach +1 = 20 = wartungsintervall
        conn.execute(
            "UPDATE gegenstand SET nutzungszaehler = ? WHERE inventarnummer = ?",
            (19, "inv-1"),
        )
        conn.commit()

        ergebnis = pruefung_abschliessen(
            repos["ausleihe"],
            repos["gegenstand"],
            repos["kategorie"],
            repos["maengel"],
            repos["pruefabschluss"],
            clock,
            "lease-1",
            [],
            500,
            "verfuegbar",
        )

        assert ergebnis.neuer_gegenstand_zustand == GegenstandZustand.WARTUNGSFAELLIG
        gegenstand = repos["gegenstand"].find_by_inventarnummer("inv-1")
        assert gegenstand.zustand == GegenstandZustand.WARTUNGSFAELLIG
        assert gegenstand.nutzungszaehler == 20

    def test_zielzustand_ausgemustert_prioritaet(self, repos, clock):
        """Priorität: ausgemustert > wartungsfaellig > verfuegbar.
        Wenn Wart 'ausgemustert' angibt, wird das gesetzt (auch wenn
        nutzungszaehler < wartungsintervall)."""
        ergebnis = pruefung_abschliessen(
            repos["ausleihe"],
            repos["gegenstand"],
            repos["kategorie"],
            repos["maengel"],
            repos["pruefabschluss"],
            clock,
            "lease-1",
            [],
            500,
            "ausgemustert",
        )

        assert ergebnis.neuer_gegenstand_zustand == GegenstandZustand.AUSGEMUSTERT

    def test_bru_rup05_neue_vs_bekannte_maengel(self, conn, repos, clock):
        """BR-RUP-05: Neue Mängel werden der Gegenstand-Liste hinzugefügt,
        Duplikate werden ignoriert (exakte Stringübereinstimmung)."""
        # Zuerst ein älteres Prüfprotokoll erstellen für die FK
        conn.execute(
            """
            INSERT INTO pruefprotokoll (pruefprotokoll_id, ausleihe_id,
                                       kautionsabzug_cent, zielzustand, erstellt_am)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("proto-old", "lease-1", 0, "verfuegbar", "2025-01-20"),
        )

        # Vorhandene Mängel: "Kratzer", "Dellen"
        conn.execute(
            """
            INSERT INTO maengel_eintrag (maengel_id, gegenstand_id,
                                        beschreibung,
                                        festgestellt_in_pruefprotokoll_id)
            VALUES (?, ?, ?, ?)
            """,
            ("dmg-1", "inv-1", "Kratzer", "proto-old"),
        )
        conn.execute(
            """
            INSERT INTO maengel_eintrag (maengel_id, gegenstand_id,
                                        beschreibung,
                                        festgestellt_in_pruefprotokoll_id)
            VALUES (?, ?, ?, ?)
            """,
            ("dmg-2", "inv-1", "Dellen", "proto-old"),
        )
        conn.commit()

        # Neue Beschreibungen: "Kratzer" (dup), "Rost" (neu), "Risse" (neu)
        ergebnis = pruefung_abschliessen(
            repos["ausleihe"],
            repos["gegenstand"],
            repos["kategorie"],
            repos["maengel"],
            repos["pruefabschluss"],
            clock,
            "lease-1",
            ["Kratzer", "Rost", "Risse"],
            500,
            "verfuegbar",
        )

        # Nur "Rost" und "Risse" sollten neu eingefügt werden
        # (In der DB, nicht in ergebnis)
        neue_maengel = conn.execute(
            """
            SELECT * FROM maengel_eintrag
            WHERE festgestellt_in_pruefprotokoll_id = ?
            ORDER BY beschreibung
            """,
            (ergebnis.pruefprotokoll_id,),
        ).fetchall()

        assert len(neue_maengel) == 2
        beschreibungen = {m["beschreibung"] for m in neue_maengel}
        assert beschreibungen == {"Risse", "Rost"}

    def test_bru_kau01_kautionsbewegungen_freigabe(self, conn, repos, clock):
        """BR-KAU-01/04: Kautionsbewegung FREIGABE mit Betrag kaution-abzug."""
        ergebnis = pruefung_abschliessen(
            repos["ausleihe"],
            repos["gegenstand"],
            repos["kategorie"],
            repos["maengel"],
            repos["pruefabschluss"],
            clock,
            "lease-1",
            [],
            500,
            "verfuegbar",
        )

        # kaution=2000, abzug=500 -> freigabe=1500
        bewegungen = conn.execute(
            """
            SELECT * FROM kautionsbewegung WHERE ausleihe_id = ? ORDER BY zeitstempel
            """,
            ("lease-1",),
        ).fetchall()

        # FREIGABE immer, ABZUG nur wenn abzug > 0
        assert len(bewegungen) == 2
        assert bewegungen[0]["art"] == "freigabe"
        assert bewegungen[0]["betrag_cent"] == 1500
        assert bewegungen[1]["art"] == "abzug"
        assert bewegungen[1]["betrag_cent"] == 500

    def test_bru_kau02_abzug_null(self, conn, repos, clock):
        """Wenn Abzug = 0, nur FREIGABE-Eintrag, kein ABZUG-Eintrag."""
        ergebnis = pruefung_abschliessen(
            repos["ausleihe"],
            repos["gegenstand"],
            repos["kategorie"],
            repos["maengel"],
            repos["pruefabschluss"],
            clock,
            "lease-1",
            [],
            0,  # abzug = 0
            "verfuegbar",
        )

        bewegungen = conn.execute(
            """
            SELECT * FROM kautionsbewegung WHERE ausleihe_id = ? ORDER BY zeitstempel
            """,
            ("lease-1",),
        ).fetchall()

        # Nur FREIGABE (kaution_cent = 2000), kein ABZUG
        assert len(bewegungen) == 1
        assert bewegungen[0]["art"] == "freigabe"
        assert bewegungen[0]["betrag_cent"] == 2000

    def test_audit_log_eintrag_erstellt(self, conn, repos, clock):
        """Audit-Log-Eintrag wird mit ereignisart='pruefung_abgeschlossen'
        eingefügt."""
        ergebnis = pruefung_abschliessen(
            repos["ausleihe"],
            repos["gegenstand"],
            repos["kategorie"],
            repos["maengel"],
            repos["pruefabschluss"],
            clock,
            "lease-1",
            [],
            500,
            "verfuegbar",
        )

        audit = conn.execute(
            "SELECT * FROM audit_log WHERE aggregat_id = ?", ("lease-1",)
        ).fetchone()
        assert audit is not None
        assert audit["ereignisart"] == "pruefung_abgeschlossen"
        assert audit["rolle"] == "wart"


# --- REST-Endpunkt Tests -----------

class TestRestPruefprotokoll:
    """REST-Tests für POST /ausleihen/{ausleiheId}/pruefprotokoll."""

    @pytest.fixture
    def client(self, conn, clock):
        """TestClient mit echtem (Memory-)SQLite Backend."""
        app = create_app(conn, clock)
        return TestClient(app)

    def test_pruefung_abschliessen_erfolg(self, client):
        """POST /ausleihen/lease-1/pruefprotokoll mit Wart-Rolle: 201."""
        response = client.post(
            "/ausleihen/lease-1/pruefprotokoll",
            json={
                "neueMaengel": [{"beschreibung": "Kratzer"}],
                "kautionsabzugCent": 500,
                "zielzustand": "verfuegbar",
            },
            headers={"X-Rolle": "wart"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "pruefprotokollId" in data
        assert data["ausleiheId"] == "lease-1"
        assert data["kautionsabzugCent"] == 500
        assert data["neuerGegenstandZustand"] == "verfuegbar"

    def test_pruefung_abschliessen_ausleihe_nicht_gefunden(self, client):
        """POST nonexistent ausleiheId: 404."""
        response = client.post(
            "/ausleihen/nonexistent/pruefprotokoll",
            json={
                "neueMaengel": [],
                "kautionsabzugCent": 500,
                "zielzustand": "verfuegbar",
            },
            headers={"X-Rolle": "wart"},
        )

        assert response.status_code == 404
        assert response.json()["detail"]["fehlercode"] == "AUSLEIHE_NICHT_GEFUNDEN"

    def test_pruefung_abschliessen_nicht_in_pruefung(self, conn, client):
        """Wenn Gegenstand nicht in_pruefung: 409."""
        conn.execute(
            "UPDATE gegenstand SET zustand = ? WHERE inventarnummer = ?",
            ("verfuegbar", "inv-1"),
        )
        conn.commit()

        response = client.post(
            "/ausleihen/lease-1/pruefprotokoll",
            json={
                "neueMaengel": [],
                "kautionsabzugCent": 500,
                "zielzustand": "verfuegbar",
            },
            headers={"X-Rolle": "wart"},
        )

        assert response.status_code == 409
        assert response.json()["detail"]["fehlercode"] == "NICHT_IN_PRUEFUNG"

    def test_pruefung_abschliessen_abzug_uebersteigt_kaution(self, client):
        """Wenn Abzug > Kaution: 422."""
        response = client.post(
            "/ausleihen/lease-1/pruefprotokoll",
            json={
                "neueMaengel": [],
                "kautionsabzugCent": 2500,
                "zielzustand": "verfuegbar",
            },
            headers={"X-Rolle": "wart"},
        )

        assert response.status_code == 422
        assert response.json()["detail"]["fehlercode"] == "ABZUG_UEBERSTEIGT_KAUTION"

    def test_pruefung_abschliessen_rolle_nicht_erforderlich(self, client):
        """Nur Wart-Rolle darf Prüfung abschließen."""
        response = client.post(
            "/ausleihen/lease-1/pruefprotokoll",
            json={
                "neueMaengel": [],
                "kautionsabzugCent": 500,
                "zielzustand": "verfuegbar",
            },
            headers={"X-Rolle": "thekendienst"},
        )

        # Rollenprüfung sollte eine 403 werfen
        assert response.status_code == 403

    def test_pruefung_abschliessen_zielzustand_ungueltig(self, client):
        """Ungültiger zielzustand: 422 (Pydantic validation)."""
        response = client.post(
            "/ausleihen/lease-1/pruefprotokoll",
            json={
                "neueMaengel": [],
                "kautionsabzugCent": 500,
                "zielzustand": "invalid",
            },
            headers={"X-Rolle": "wart"},
        )

        assert response.status_code == 422
