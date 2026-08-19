"""Anwendungsdienst für UC-05 (Wartung abschließen) / SI-06.

IOSP: Validierung (kein Port-Zugriff) ist von Integration (Repository-Aufrufe)
getrennt. Verfügbarkeit der Repositories ist explizit: gegenstand_repo,
kategorie_repo, vormerkung_repo.
"""
from dataclasses import dataclass

from leihgut.domain.gegenstand import Gegenstand, GegenstandZustand
from leihgut.ports.gegenstand_repository import GegenstandRepository
import json
from leihgut.domain.audit_log import AuditLogEintrag
from leihgut.ports.audit_log_repository import AuditLogRepository
from leihgut.ports.clock import Clock
from leihgut.ports.kategorie_repository import KategorieRepository
from leihgut.ports.vormerkung_repository import VormerkungRepository


@dataclass(frozen=True)
class GegenstandNichtGefunden:
    """SI-06-Ablehnung: `404 GEGENSTAND_NICHT_GEFUNDEN`."""

    inventarnummer: str


@dataclass(frozen=True)
class NichtWartungsfaellig:
    """SI-06-Ablehnung: `409 NICHT_WARTUNGSFAELLIG` — Gegenstand ist nicht
    im Zustand wartungsfaellig (Voraussetzung: UC-04 muss wartungsfällig
    gesetzt haben)."""

    inventarnummer: str


WartungAblehnung = GegenstandNichtGefunden | NichtWartungsfaellig


@dataclass(frozen=True)
class WartungErgebnis:
    """Antwortmodell für SI-06: `{inventarnummer, zustand, nutzungszaehler}`."""

    inventarnummer: str
    zustand: GegenstandZustand
    nutzungszaehler: int


# --- Operation: Validierung (kein Port-Zugriff) --------------------


def _wartung_pruefen(
    zustand: GegenstandZustand | None,
) -> WartungAblehnung | None:
    """Validierungsreihenfolge: Gegenstand wartungsfaellig? (BR-WAR-03)."""
    if zustand != GegenstandZustand.WARTUNGSFAELLIG:
        return NichtWartungsfaellig("unknown")
    return None


# --- Integration: Wartung abschließen (UC-05) ---------------------------


def wartung_abschliessen(
    gegenstand_repo: GegenstandRepository,
    kategorie_repo: KategorieRepository,
    vormerkung_repo: VormerkungRepository,
    audit_log_repo: AuditLogRepository,
    clock: Clock,
    inventarnummer: str,
    rolle: str = "wart",
) -> WartungErgebnis | WartungAblehnung:
    """Wartung abschließen (UC-05 / SI-06).

    Validierungsreihenfolge:
    1. Gegenstand existiert (404)
    2. Gegenstand ist wartungsfaellig (409)
    3. Check Vormerkung (BR-VOR-03) → Zustand bestimmen

    BR-WAR-03: Gegenstand verfügbar setzen, Nutzungszähler → 0
    BR-VOR-03: Wenn Vormerkung existiert → RESERVIERT, sonst VERFUEGBAR
    """
    # Schritt 1: Gegenstand existiert?
    gegenstand = gegenstand_repo.find_by_inventarnummer(inventarnummer)
    if gegenstand is None:
        return GegenstandNichtGefunden(inventarnummer)

    # Schritt 2: Gegenstand wartungsfaellig?
    ablehnung = _wartung_pruefen(gegenstand.zustand)
    if ablehnung is not None:
        return NichtWartungsfaellig(inventarnummer)

    # Schritt 3: Kategorie laden
    kategorie = kategorie_repo.find_by_id(gegenstand.kategorie_id)
    if kategorie is None:
        # Nicht erwartet (Datenkonsistenz-Fehler), aber sicherheitshalber
        return GegenstandNichtGefunden(inventarnummer)

    # Schritt 4: Offene Vormerkung für Kategorie suchen (BR-VOR-03)
    offene_vormerkungen = (
        vormerkung_repo.find_offene_je_kategorie_sortiert_nach_reihenfolge(
            gegenstand.kategorie_id
        )
    )

    # Schritt 5: Zielzustand bestimmen
    if offene_vormerkungen:
        # Erste Vormerkung existiert → Gegenstand wird RESERVIERT
        folgezustand = GegenstandZustand.RESERVIERT
    else:
        # Keine Vormerkung → Gegenstand wird VERFUEGBAR
        folgezustand = GegenstandZustand.VERFUEGBAR

    # Schritt 6: Gegenstand aktualisieren (BR-WAR-03: nutzungszaehler → 0)
    aktualisierter_gegenstand = Gegenstand(
        inventarnummer=gegenstand.inventarnummer,
        kategorie_id=gegenstand.kategorie_id,
        zustand=folgezustand,
        wiederbeschaffungswert_cent=gegenstand.wiederbeschaffungswert_cent,
        nutzungszaehler=0,
    )
    gegenstand_repo.update(aktualisierter_gegenstand)
    
    # Audit-Eintrag (UC-05, BR-WAR-03)
    audit_log_repo.insert(AuditLogEintrag(
        zeitstempel=clock.jetzt(),
        aggregat="Gegenstand",
        aggregat_id=inventarnummer,
        ereignisart="zustand_geaendert",
        rolle=rolle,
        werte_vorher=json.dumps({"zustand": gegenstand.zustand.value, "nutzungszaehler": gegenstand.nutzungszaehler}),
        werte_nachher=json.dumps({"zustand": folgezustand.value, "nutzungszaehler": 0}),
    ))

    return WartungErgebnis(
        inventarnummer=inventarnummer,
        zustand=folgezustand,
        nutzungszaehler=0,
    )
