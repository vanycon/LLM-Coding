"""Domänenmodell: Kautionsbewegung (BR-KAU-01, BR-KAU-04, UC-04/UC-06).

`HINTERLEGUNG` ist laut Entity-Modell (`spec-domain-model.adoc`) ein gültiger
Bewegungstyp, wird aber in dieser Codebasis (noch) nicht erzeugt: die
Rückverfolgbarkeitstabelle in `spec.adoc` ordnet BR-KAU-01/04 ausschließlich
UC-04 zu, nicht UC-01 (siehe Analyse zu User Story B1,
`epic-b-pruefung-kaution.adoc`). `ABZUG` und `FREIGABE` entstehen beim
Prüfabschluss (UC-04); `VERLUST_EINZUG` entsteht bei Verlustmeldung (UC-06).
"""
from dataclasses import dataclass
from enum import Enum


class KautionsbewegungArt(str, Enum):
    HINTERLEGUNG = "hinterlegung"
    ABZUG = "abzug"
    FREIGABE = "freigabe"
    VERLUST_EINZUG = "verlust_einzug"


@dataclass(frozen=True)
class Kautionsbewegung:
    bewegung_id: str
    ausleihe_id: str
    art: KautionsbewegungArt
    betrag_cent: int
    zeitstempel: str
    ausloeser: str
