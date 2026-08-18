"""Domänenmodell: Audit-Log-Eintrag (ADR-009, `04_solution_strategy.adoc`
Abschnitt Nachvollziehbarkeit).

Erster Anwendungsdienst, der tatsächlich einen Eintrag schreibt (siehe
Analyse zu User Story B1, `epic-b-pruefung-kaution.adoc`); frühere EPICs
(UC-01/03/07/08/09) schreiben noch keinen Audit-Eintrag — bekannter, hier
nicht mitbehobener Altbestand.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditLogEintrag:
    zeitstempel: str
    aggregat: str
    aggregat_id: str
    ereignisart: str
    rolle: str
    werte_vorher: str | None = None
    werte_nachher: str | None = None
