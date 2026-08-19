"""Pydantic-Schemas für die Katalogpflege- (SI-09), Einweisungs- (SI-07/SI-08),
und Vormerkung-Endpunkte (SI-05)."""
from typing import Literal

from pydantic import BaseModel, Field


class KategorieAnlegenRequest(BaseModel):
    kategorieId: str
    name: str
    leihdauerTage: int
    wartungsintervall: int
    einweisungspflichtig: bool


class KategorieAendernRequest(BaseModel):
    leihdauerTage: int
    wartungsintervall: int
    einweisungspflichtig: bool


class GegenstandAnlegenRequest(BaseModel):
    inventarnummer: str
    kategorieId: str
    wiederbeschaffungswertCent: int


class GegenstandAendernRequest(BaseModel):
    wiederbeschaffungswertCent: int


class EinweisungErfassenRequest(BaseModel):
    mitgliedId: str
    kategorieId: str


class VormerkungErfassenRequest(BaseModel):
    mitgliedId: str
    kategorieId: str


class GegenstandAusgebenRequest(BaseModel):
    mitgliedId: str


class GegenstandZuruecknehmenRequest(BaseModel):
    auffaelligkeiten: str | None = None


class MangelEintragRequest(BaseModel):
    beschreibung: str


class PruefungAbschliessenRequest(BaseModel):
    neueMaengel: list[MangelEintragRequest] = []
    kautionsabzugCent: int = Field(ge=0)
    zielzustand: Literal["verfuegbar", "ausgemustert"]
