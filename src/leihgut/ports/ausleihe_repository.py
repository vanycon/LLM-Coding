"""Port für den Zugriff auf Ausleihen (UC-01/UC-03, SI-01/SI-03)."""
from typing import Protocol

from leihgut.domain.ausleihe import Ausleihe


class NebenlaeufigeAusgabeAbgelehnt(Exception):
    """Wird von `insert()` ausgelöst, wenn der partielle Unique-Index
    `ux_ausleihe_aktiv_je_gegenstand` (ADR-007) eine zweite gleichzeitig
    aktive Ausleihe desselben Gegenstands verhindert hat — die
    Anwendungsprüfung (BR-AUS-01) hatte zu diesem Zeitpunkt bereits grünes
    Licht gegeben, wurde aber von einer parallelen Anfrage überholt.
    Framework-agnostisch, damit der Anwendungskern kein `sqlite3`
    importieren muss (ADR-002)."""


class AusleiheRepository(Protocol):
    def find_by_id(self, ausleihe_id: str) -> Ausleihe | None:
        """Liefert die Ausleihe oder ``None`` (SI-02, SI-03, SI-04, SI-06)."""
        ...

    def finde_offene_fuer_mitglied(self, mitglied_id: str) -> list[Ausleihe]:
        """Liefert alle Ausleihen des Mitglieds in den Zuständen `aktiv`
        oder `zurueckgegeben` (BR-AUS-02: zählen gegen das
        Drei-Ausleihen-Limit; BR-SPE-01/02: Grundlage für die
        Sperrprüfung, deren `aktiv`-Teilmenge der Aufrufer selbst gegen
        die Rückgabefrist prüft)."""
        ...

    def insert(self, ausleihe: Ausleihe) -> None:
        """Legt eine neue Ausleihe an (SI-01). Öffnet die Transaktion mit
        `BEGIN IMMEDIATE` (ADR-007): die Schreibsperre wird vor der
        Prüfung genommen, nicht erst beim Schreiben. Der partielle
        Unique-Index `ux_ausleihe_aktiv_je_gegenstand` ist die zweite,
        DB-erzwungene Schranke gegen zwei aktive Ausleihen desselben
        Gegenstands und kann `sqlite3.IntegrityError` auslösen, wenn eine
        TOCTOU-Race die Anwendungsprüfung überholt hat."""
        ...

    def update(self, ausleihe: Ausleihe) -> None:
        """Aktualisiert eine bestehende Ausleihe (SI-03, u. a. Zustand,
        Auffälligkeiten)."""
        ...
