"""Domänenmodell für Ausleihen (UC-01/UC-03, BR-AUS-01..05).

Zustandswerte nach `spec-domain-model.adoc`, Abschnitt "Zustandsautomaten":
`aktiv → zurueckgegeben → abgeschlossen`, bzw. `aktiv → abgeschlossen_verloren`
bei Verlust (UC-06). `kaution_cent` ist ein bei der Ausgabe berechneter
Snapshot (BR-KAT-04) — siehe `docs/implementation/epic-a-ausleihe-kernprozess.adoc`,
Analyse zu User Story A1, zur Begründung, warum hier kein separates
`Kautionsbewegung`-Ledger geführt wird.
"""
from dataclasses import dataclass
from enum import Enum


class AusleiheZustand(str, Enum):
    AKTIV = "aktiv"
    ZURUECKGEGEBEN = "zurueckgegeben"
    ABGESCHLOSSEN = "abgeschlossen"
    ABGESCHLOSSEN_VERLOREN = "abgeschlossen_verloren"


@dataclass(frozen=True)
class Ausleihe:
    ausleihe_id: str
    gegenstand_id: str
    mitglied_id: str
    ausgabedatum: str
    rueckgabefrist: str
    kaution_cent: int
    verlaengert: bool = False
    zustand: AusleiheZustand = AusleiheZustand.AKTIV
    rueckgabe_auffaelligkeiten: str | None = None

    def ist_ueberfaellig(self, heute: str) -> bool:
        """BR-SPE-02: `rueckgabefrist < heute AND zustand NOT IN
        (zurueckgegeben, abgeschlossen, abgeschlossen_verloren)` — reduziert
        sich auf den Zustand `aktiv`, da das der einzige verbleibende Wert
        in unserem Zustandsraum ist (siehe Analyse in
        `epic-a-ausleihe-kernprozess.adoc`)."""
        return self.zustand == AusleiheZustand.AKTIV and self.rueckgabefrist < heute
