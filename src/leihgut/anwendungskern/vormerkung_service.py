"""Anwendungsdienst für UC-05 (Vormerkung erfassen) / SI-05.

IOSP: Reine Validierung ist von der Integration (Repository-Aufrufe) getrennt.
"""
import uuid
from dataclasses import dataclass

from leihgut.domain.vormerkung import Vormerkung, VormerkungStatus
from leihgut.ports.vormerkung_repository import VormerkungRepository
from leihgut.ports.kategorie_repository import KategorieRepository
from leihgut.ports.clock import Clock


@dataclass(frozen=True)
class KategorieNichtGefunden:
    """SI-05-Ablehnung: `404 KATEGORIE_NICHT_GEFUNDEN`."""

    kategorie_id: str


@dataclass(frozen=True)
class MitgliedGesperrt:
    """SI-05-Ablehnung: `409 MITGLIED_GESPERRT` (BR-VOR-??)."""

    mitglied_id: str


@dataclass(frozen=True)
class DuplikatVormerkung:
    """SI-05-Ablehnung: `409 DUPLIKAT_VORMERKUNG` (BR-VOR-01)."""

    mitglied_id: str
    kategorie_id: str


@dataclass(frozen=True)
class VormerkungNichtGefunden:
    """SI-05-Ablehnung: `404 VORMERKUNG_NICHT_GEFUNDEN` (GET Abfrage)."""

    vormerkung_id: str


VormerkungAblehnung = (
    KategorieNichtGefunden | MitgliedGesperrt | DuplikatVormerkung | VormerkungNichtGefunden
)


# --- Operation: Reihenfolge berechnen ---


def _reihenfolge_berechnen(offene_vormerkungen: list[Vormerkung]) -> int:
    """BR-VOR-02: Reihenfolge = count(offene) + 1 (FIFO)."""
    return len([v for v in offene_vormerkungen if v.ist_offen()]) + 1


# --- Integration: Vormerkung erfassen (UC-05 / SI-05) ---


def vormerkung_erfassen(
    vormerkung_repo: VormerkungRepository,
    kategorie_repo: KategorieRepository,
    clock: Clock,
    mitglied_id: str,
    kategorie_id: str,
    gesperrte_mitglieder: list[str] | None = None,
) -> Vormerkung | VormerkungAblehnung:
    """Vormerkung erfassen (UC-05 / SI-05).

    Validierungsreihenfolge:
    1. Kategorie existiert (404)
    2. Mitglied nicht gesperrt (409)
    3. Keine offene Vormerkung für (Mitglied, Kategorie) existiert (409, BR-VOR-01)
    """
    if gesperrte_mitglieder is None:
        gesperrte_mitglieder = []

    # Prüfe: Kategorie existiert
    if kategorie_repo.find_by_id(kategorie_id) is None:
        return KategorieNichtGefunden(kategorie_id)

    # Prüfe: Mitglied nicht gesperrt
    if mitglied_id in gesperrte_mitglieder:
        return MitgliedGesperrt(mitglied_id)

    # Prüfe: Keine offene Vormerkung vorhanden (BR-VOR-01)
    bestehende = vormerkung_repo.find_offene_je_mitglied_kategorie(
        mitglied_id, kategorie_id
    )
    if bestehende is not None:
        return DuplikatVormerkung(mitglied_id, kategorie_id)

    # Berechne Reihenfolge
    offene_fuer_kategorie = (
        vormerkung_repo.find_offene_je_kategorie_sortiert_nach_reihenfolge(kategorie_id)
    )
    reihenfolge = _reihenfolge_berechnen(offene_fuer_kategorie)

    # Anlegen: neue Vormerkung mit status = "offen"
    jetzt = clock.jetzt()
    neue_vormerkung = Vormerkung(
        vormerkung_id=str(uuid.uuid4()),
        kategorie_id=kategorie_id,
        mitglied_id=mitglied_id,
        erstellt_am=jetzt,
        status=VormerkungStatus.OFFEN,
        reihenfolge=reihenfolge,
    )
    vormerkung_repo.insert(neue_vormerkung)

    # Nach Insert: nochmal lesen, um die generierte ID zu bekommen
    gerade_angelegt = vormerkung_repo.find_offene_je_mitglied_kategorie(
        mitglied_id, kategorie_id
    )
    assert gerade_angelegt is not None
    return gerade_angelegt


# --- Integration: Vormerkungs verwalten nach Rückgabe (UC-03 Integration) ---


def vormerkungs_verwalten_nach_rueckgabe(
    vormerkung_repo: VormerkungRepository,
    kategorie_id: str,
) -> Vormerkung | None:
    """Nach erfolgreicher Rückgabe eines Gegenstands: Erste offene
    Vormerkung automatisch absagen (BR-VOR-02 FIFO + "nicht innerhalb von
    7 Tagen abgerufen").

    Liefert die abgesagte Vormerkung oder None, falls keine vorhanden.
    """
    offene = vormerkung_repo.find_offene_je_kategorie_sortiert_nach_reihenfolge(
        kategorie_id
    )
    if not offene:
        return None

    erste = offene[0]
    automatisch_abgesagte = Vormerkung(
        vormerkung_id=erste.vormerkung_id,
        kategorie_id=erste.kategorie_id,
        mitglied_id=erste.mitglied_id,
        erstellt_am=erste.erstellt_am,
        status=VormerkungStatus.AUTOMATISCH_ABGESAGT,
        reihenfolge=erste.reihenfolge,
    )
    vormerkung_repo.update(automatisch_abgesagte)
    return automatisch_abgesagte


# --- Integration: Vormerkung abrufen (GET /vormerkungen/{id}) ---


def vormerkung_abrufen(
    vormerkung_repo: VormerkungRepository, vormerkung_id: str
) -> Vormerkung | VormerkungNichtGefunden:
    """Vormerkung abrufen nach ID (GET /vormerkungen/{id} / SI-05).

    Liefert die Vormerkung oder VormerkungNichtGefunden (404).
    """
    gefundene = vormerkung_repo.find_by_id(vormerkung_id)
    if gefundene is None:
        return VormerkungNichtGefunden(vormerkung_id)
    return gefundene
