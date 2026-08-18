"""Clock-Port (ADR-006, `09_architecture_decisions.adoc`).

Der Anwendungskern liest "heute"/"jetzt" ausschließlich über diesen Port,
nie über einen direkten `datetime.now()`-Aufruf im Domänenmodell oder in
den Anwendungsdiensten. So bleiben fristabhängige Regeln (Rückgabefrist,
Reservierungsverfall, Sperre, hier: `erstelltAm`/`widerrufenAm` einer
Einweisung) mit einem Fake-Datum reproduzierbar testbar
(`05_building_block_view.adoc`: "Anwendungskern ↔ Zeitquelle-Adapter:
`Clock.heute() -> Datum`").
"""
from typing import Protocol


class Clock(Protocol):
    def jetzt(self) -> str:
        """Liefert den aktuellen Zeitpunkt als ISO-8601-String
        (`YYYY-MM-DDTHH:MM:SS`), UTC."""
        ...
