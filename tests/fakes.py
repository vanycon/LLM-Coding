"""Test-Doubles für Ports, die über mehrere Testdateien hinweg gebraucht
werden (ADR-006: `Clock`-Port wird in Tests durch einen Fake mit festem
Datum ersetzt statt echter Zeit)."""


class FakeClock:
    def __init__(self, jetzt: str = "2026-08-18T10:00:00") -> None:
        self._jetzt = jetzt

    def jetzt(self) -> str:
        return self._jetzt
