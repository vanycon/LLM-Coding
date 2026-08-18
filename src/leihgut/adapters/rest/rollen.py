"""Zentrale Rollenprüfung an der Systemgrenze (08_concepts.adoc, Abschnitt
Sicherheit: "Jeder Adapter, der Anwendungsdienste aufruft, muss die
mitgegebene Rolle gegen die Rollenmatrix prüfen, *bevor* er den
Anwendungsdienst aufruft").

Die Rolle wird per Header ``X-Rolle`` übergeben und *nicht* kryptografisch
geprüft (PRD, "Rahmenbedingungen"; Bedrohungsmodell T-004, R-001) — das ist
eine bewusste, dokumentierte Einschränkung, keine Falle in diesem Modul.
"""
from fastapi import Header, HTTPException


def erfordere_rolle(*erlaubte_rollen: str):
    """Erzeugt eine FastAPI-Dependency, die den `X-Rolle`-Header gegen die
    übergebenen erlaubten Rollen prüft und bei Nichterfüllung mit
    `403 ROLLE_NICHT_BERECHTIGT` ablehnt (Fehlercode-Übersicht,
    spec-system-interfaces.adoc: "gilt für alle" Endpunkte)."""

    def dependency(x_rolle: str = Header(...)) -> str:
        if x_rolle not in erlaubte_rollen:
            raise HTTPException(
                status_code=403,
                detail={"fehlercode": "ROLLE_NICHT_BERECHTIGT"},
            )
        return x_rolle

    return dependency
