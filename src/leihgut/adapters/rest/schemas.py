"""Pydantic-Schemas für die Katalogpflege- (SI-09) und Einweisungs-Endpunkte
(SI-07/SI-08)."""
from pydantic import BaseModel


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


class GegenstandAusgebenRequest(BaseModel):
    mitgliedId: str


class GegenstandZuruecknehmenRequest(BaseModel):
    auffaelligkeiten: str | None = None
