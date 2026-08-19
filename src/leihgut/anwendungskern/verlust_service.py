"""Anwendungsdienst für UC-06 (Gegenstand als verloren melden) / SI-06.

IOSP: Validierung ist von der Integration (Repository-Aufrufe) getrennt.
"""
import json
import sqlite3
import uuid
from dataclasses import dataclass

from leihgut.domain.audit_log import AuditLogEintrag
from leihgut.domain.ausleihe import Ausleihe, AusleiheZustand
from leihgut.domain.gegenstand import Gegenstand, GegenstandZustand
from leihgut.domain.kautionsbewegung import Kautionsbewegung, KautionsbewegungArt
from leihgut.ports.audit_log_repository import AuditLogRepository
from leihgut.ports.ausleihe_repository import AusleiheRepository
from leihgut.ports.gegenstand_repository import GegenstandRepository
from leihgut.ports.clock import Clock


@dataclass(frozen=True)
class AusleiheNichtGefunden:
    """SI-06-Ablehnung: `404 AUSLEIHE_NICHT_GEFUNDEN`."""

    ausleihe_id: str


@dataclass(frozen=True)
class AusleiheNichtAktiv:
    """SI-06-Ablehnung: `409 AUSLEIHE_NICHT_AKTIV` (nur aktive Ausleihen können verloren sein)."""

    ausleihe_id: str
    aktueller_zustand: str


@dataclass(frozen=True)
class GegenstandNichtGefunden:
    """SI-06-Ablehnung: `404 GEGENSTAND_NICHT_GEFUNDEN` (sollte nicht vorkommen, wenn Konsistenz gewährleistet)."""

    inventarnummer: str


VerlustAblehnung = AusleiheNichtGefunden | AusleiheNichtAktiv | GegenstandNichtGefunden


# --- Integration: Verlust erfassen (UC-06 / SI-06) ---


def verlust_erfassen(
    conn: sqlite3.Connection,
    ausleihe_repo: AusleiheRepository,
    gegenstand_repo: GegenstandRepository,
    audit_log_repo: AuditLogRepository,
    clock: Clock,
    ausleihe_id: str,
    rolle: str = "wart",
) -> Ausleihe | VerlustAblehnung:
    """Verlust erfassen (UC-06 / SI-06).

    Validierungsreihenfolge (BR-VER-02):
    1. Ausleihe existiert (404)
    2. Ausleihe ist aktiv (409)
    3. Gegenstand existiert (404, sollte nicht vorkommen)

    Aktion (BR-VER-01/02/03, BR-KAU-03/04):
    - Ausleihe → ABGESCHLOSSEN_VERLOREN
    - Gegenstand → AUSGEMUSTERT
    - Kautionsbewegung: 100% Einzug (art=verlust_einzug)
    """
    # Prüfe: Ausleihe existiert
    bestehende_ausleihe = ausleihe_repo.find_by_id(ausleihe_id)
    if bestehende_ausleihe is None:
        return AusleiheNichtGefunden(ausleihe_id)

    # Prüfe: Ausleihe ist aktiv (BR-VER-02: nur aktive Ausleihen können verloren sein)
    if bestehende_ausleihe.zustand != AusleiheZustand.AKTIV:
        return AusleiheNichtAktiv(ausleihe_id, bestehende_ausleihe.zustand.value)

    # Prüfe: Gegenstand existiert (Konsistenz-Check)
    gegenstand = gegenstand_repo.find_by_inventarnummer(bestehende_ausleihe.gegenstand_id)
    if gegenstand is None:
        return GegenstandNichtGefunden(bestehende_ausleihe.gegenstand_id)

    # --- Aktion: Verlust erfassen (atomare Transaktion) ---
    # Starte Transaktion nur, wenn keine bereits läuft
    try:
        conn.execute("BEGIN IMMEDIATE")
        started_transaction = True
    except sqlite3.OperationalError:
        # Transaktion läuft bereits
        started_transaction = False
    
    try:
        # Ausleihe abschließen als verloren
        ausleihe_verloren = Ausleihe(
            ausleihe_id=bestehende_ausleihe.ausleihe_id,
            gegenstand_id=bestehende_ausleihe.gegenstand_id,
            mitglied_id=bestehende_ausleihe.mitglied_id,
            ausgabedatum=bestehende_ausleihe.ausgabedatum,
            rueckgabefrist=bestehende_ausleihe.rueckgabefrist,
            kaution_cent=bestehende_ausleihe.kaution_cent,
            verlaengert=bestehende_ausleihe.verlaengert,
            zustand=AusleiheZustand.ABGESCHLOSSEN_VERLOREN,  # BR-VER-02
            rueckgabe_auffaelligkeiten=None,
            mitglied_gesperrt=bestehende_ausleihe.mitglied_gesperrt,
        )
        conn.execute(
            "UPDATE ausleihe SET zustand = ? WHERE ausleihe_id = ?",
            (AusleiheZustand.ABGESCHLOSSEN_VERLOREN.value, ausleihe_id),
        )

        # Gegenstand ausmustern
        gegenstand_ausgemustert = Gegenstand(
            inventarnummer=gegenstand.inventarnummer,
            kategorie_id=gegenstand.kategorie_id,
            zustand=GegenstandZustand.AUSGEMUSTERT,  # BR-VER-03
            wiederbeschaffungswert_cent=gegenstand.wiederbeschaffungswert_cent,
            nutzungszaehler=gegenstand.nutzungszaehler,
        )
        conn.execute(
            "UPDATE gegenstand SET zustand = ? WHERE inventarnummer = ?",
            (GegenstandZustand.AUSGEMUSTERT.value, gegenstand.inventarnummer),
        )

        # Kaution 100% einbehalten (BR-KAU-03/04)
        kautionsbewegung = Kautionsbewegung(
            bewegung_id=str(uuid.uuid4()),
            ausleihe_id=ausleihe_id,
            art=KautionsbewegungArt.VERLUST_EINZUG,
            betrag_cent=bestehende_ausleihe.kaution_cent,  # Positive: Betrag das einbehalten wird
            zeitstempel=clock.jetzt(),
            ausloeser=rolle,
        )
        conn.execute(
            "INSERT INTO kautionsbewegung "
            "(bewegung_id, ausleihe_id, art, betrag_cent, zeitstempel, ausloeser) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                kautionsbewegung.bewegung_id,
                kautionsbewegung.ausleihe_id,
                kautionsbewegung.art.value,
                kautionsbewegung.betrag_cent,
                kautionsbewegung.zeitstempel,
                kautionsbewegung.ausloeser,
            ),
        )
        
        # Audit-Einträge (UC-06, BR-VER-01/02)
        audit_log_repo.insert(AuditLogEintrag(
            zeitstempel=clock.jetzt(),
            aggregat="Ausleihe",
            aggregat_id=ausleihe_id,
            ereignisart="zustand_geaendert",
            rolle=rolle,
            werte_vorher=json.dumps({"zustand": bestehende_ausleihe.zustand.value}),
            werte_nachher=json.dumps({"zustand": AusleiheZustand.ABGESCHLOSSEN_VERLOREN.value}),
        ))
        audit_log_repo.insert(AuditLogEintrag(
            zeitstempel=clock.jetzt(),
            aggregat="Gegenstand",
            aggregat_id=gegenstand.inventarnummer,
            ereignisart="zustand_geaendert",
            rolle=rolle,
            werte_vorher=json.dumps({"zustand": gegenstand.zustand.value}),
            werte_nachher=json.dumps({"zustand": GegenstandZustand.AUSGEMUSTERT.value}),
        ))

        if started_transaction:
            conn.commit()
        return ausleihe_verloren

    except Exception:
        if started_transaction:
            conn.rollback()
        raise

