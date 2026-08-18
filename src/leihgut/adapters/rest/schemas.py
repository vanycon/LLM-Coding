"""Pydantic-Schemas für die Katalogpflege-Endpunkte (SI-09)."""
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
