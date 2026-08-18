"""Domänenmodell: MaengelEintrag (BR-RUP-05, UC-04).

Strukturierte Mängelliste je Gegenstand (`prd-klaerungen.adoc`) — kein
Freitextvergleich früherer Prüfprotokolle: ein neu gemeldeter Schaden gilt
als bereits bekannt, wenn seine `beschreibung` exakt mit einem bestehenden
Eintrag für denselben Gegenstand übereinstimmt.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class MaengelEintrag:
    maengel_id: str
    gegenstand_id: str
    beschreibung: str
    festgestellt_in_pruefprotokoll_id: str
