"""Domänenmodell: Pruefprotokoll (BR-RUP-03..06, UC-04).

`neue_maengel_ids` wird nicht redundant in `schema.sql` gespeichert — die
Beziehung ergibt sich aus `MaengelEintrag.festgestellt_in_pruefprotokoll_id`
(Rückwärtsabfrage). Das Feld existiert hier nur für die Antworttreue zum
Entity-Modell (`spec-domain-model.adoc`).
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Pruefprotokoll:
    pruefprotokoll_id: str
    ausleihe_id: str
    kautionsabzug_cent: int
    zielzustand: str
    erstellt_am: str
    neue_maengel_ids: list[str] = field(default_factory=list)
