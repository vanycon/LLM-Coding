"""Produktionsimplementierung des `Clock`-Ports (ADR-006): liefert die
echte Systemzeit. Tests verwenden stattdessen einen Fake mit festem Datum
(siehe `tests/fakes.py`)."""
from datetime import UTC, datetime

from leihgut.ports.clock import Clock


class SystemClock:
    """Erfüllt den `Clock`-Port über `datetime.now(UTC)`."""

    def jetzt(self) -> str:
        return datetime.now(UTC).replace(microsecond=0, tzinfo=None).isoformat()
