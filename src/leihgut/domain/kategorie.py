"""Domänenmodell: Kategorie (UC-09 Katalog pflegen).

Siehe src/docs/specs/spec-domain-model.adoc, Entity-Modell, und
src/docs/specs/spec.adoc, BR-KAT-02.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Kategorie:
    kategorie_id: str
    name: str
    leihdauer_tage: int
    wartungsintervall: int
    einweisungspflichtig: bool
