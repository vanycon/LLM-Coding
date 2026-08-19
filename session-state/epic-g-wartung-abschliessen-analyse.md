# EPIC-G: UC-05 Wartung abschließen — Analyse

## Phase 1: ANALYZE

### Business Rules
- **BR-WAR-03**: Wart setzt wartungsfälligen Gegenstand auf `verfügbar` und Nutzungszähler → 0
- **BR-WAR-04**: Wartungsfälliger Gegenstand wird nicht ausgegeben/reserviert (bereits in Validierung)
- **BR-VOR-03**: Erste offene Vormerkung der Kategorie reserviert den Gegenstand

### UC-05 Flow (Fully Dressed)
**Precondition**: Gegenstand im Zustand `wartungsfaellig`
**Trigger**: Wart hat Wartung durchgeführt

#### Main Success Scenario
1. Wart wählt wartungsfälligen Gegenstand
2. System validiert: Gegenstand `wartungsfaellig`? 
   - ❌ Nein → 409 Ablehnung
3. System setzt Gegenstand auf `verfügbar`, Nutzungszähler → 0 (BR-WAR-03)
4. System prüft: Offene Vormerkung für Kategorie? (BR-VOR-03)
   - ✅ Ja → Gegenstand → `RESERVIERT`
   - ❌ Nein → Gegenstand bleibt `VERFUEGBAR`
5. System speichert Änderung atomar
**Postcondition**: Gegenstand `verfügbar` oder `reserviert`, Nutzungszähler = 0

### EARS-Anforderungen
- **REQ-UC05-01**: Wenn Wartung für nicht-wartungsfälligen Gegenstand → ablehnen
- **REQ-UC05-02**: Wenn Wartung abgeschlossen → Gegenstand verfügbar, Nutzungszähler = 0

### Key Design Decisions

#### 1. Zustandsübergang ohne Ausleihe
- **Why**: Nach Wartung gibt es keine "Rückmeldung" einer Ausleihe. Der Gegenstand wird direkt wieder verfügbar.
- **vs. UC-03/04**: Diese haben Ausleihen, die zurückkommen oder geprüft werden
- **Implementation**: Neuer Service `wartung_service.py` mit direkter `GegenstandRepository.update()`

#### 2. Reservierung (RESERVIERT-Zustand) ist neu
- **Current State**: Prüfung (UC-04) setzt Gegenstand auf `VERFUEGBAR`, aber reserviert nicht
  - Grund: Kommentar in pruefung_service: "Vormerkung existiert erst ab EPIC-E"
  - Tatsächlich: EPIC-E (UC-11) existiert bereits, aber Reservierung nicht umgesetzt
- **UC-05 ist first-user**: Erste UC, die einen `VERFUEGBAR` → `RESERVIERT` Übergang braucht
- **Why RESERVIERT state**: Gegenstand ist reserviert für das erste Mitglied der Warteschlange
  - Ausleihe-Prüfung (UC-01) muss dann prüfen: Ist Gegenstand für dieses Mitglied reserviert?

#### 3. Atomare Transaktion
- **Pattern**: `gegenstand_repo.update()` als eine DB-Operation
- **No separate port needed**: Kategorien sind unveränderlich (werden nur gelesen)

### Acceptance Criteria (Gherkin)

```gherkin
Feature: UC-05 Wartung abschließen
  Scenario: Wartung auf wartungsfälligen Gegenstand durchführen → verfügbar
    Given ein Gegenstand im Zustand "wartungsfaellig" mit nutzungszaehler = 3
    And keine Vormerkung für die Kategorie existiert
    When der Wart die Wartung abschließt
    Then ist der Gegenstand "verfuegbar"
    And der nutzungszaehler = 0

  Scenario: Wartung mit Vormerkung → Gegenstand wird reserviert
    Given ein Gegenstand im Zustand "wartungsfaellig"
    And eine offene Vormerkung für die Kategorie existiert (Mitglied M1)
    When der Wart die Wartung abschließt
    Then ist der Gegenstand "reserviert"
    And der nutzungszaehler = 0
    And die Vormerkungs-Reihenfolge bleibt erhalten

  Scenario: Wartung auf nicht-wartungsfälligen Gegenstand abgelehnt
    Given ein Gegenstand im Zustand "verfuegbar" (nicht wartungsfaellig)
    When der Wart versucht, Wartung abzuschließen
    Then wird die Anfrage abgelehnt mit 409 NICHT_WARTUNGSFAELLIG
```

### Data Model (No Changes)
- `Gegenstand`: bereits `zustand: GegenstandZustand` mit `WARTUNGSFAELLIG`, `VERFUEGBAR`, `RESERVIERT`
- `Gegenstand.nutzungszaehler`: bereits vorhanden
- `Kategorie.wartungsintervall`: bereits vorhanden
- `Vormerkung`: bereits vorhanden mit Status und Reihenfolge

### REST API (New Endpoint)

```
POST /wartungen
Request:
  {
    "inventarnummer": "INV-001",
    "ausloeser_rolle": "wart"
  }
Response 200:
  {
    "inventarnummer": "INV-001",
    "zustand": "verfuegbar",  # or "reserviert"
    "nutzungszaehler": 0
  }
Response 404: GEGENSTAND_NICHT_GEFUNDEN
Response 409: NICHT_WARTUNGSFAELLIG
Response 403: ROLLE_ERFORDERLICH (nur "wart")
```

### Test Strategy
1. **Service Validations** (test_wartung_service.py)
   - Gegenstand nicht gefunden → 404
   - Gegenstand nicht wartungsfaellig → 409
   
2. **Service Happy Paths**
   - Wartung: wartungsfaellig → verfuegbar, nutzungszaehler = 0
   - Wartung mit Vormerkung: wartungsfaellig → reserviert, nutzungszaehler = 0
   
3. **REST Contract Tests**
   - POST /wartungen Success (200)
   - Not found (404)
   - Not in maintenance state (409)
   - Role required (403)

### Implementation Order
1. Create `wartung_service.py` with `wartung_abschliessen()` function
2. Create REST endpoint in `app.py`
3. Create comprehensive test suite
4. Verify: no regressions in existing 162 tests

---

## Phase 2: DESIGN (Preview)

### Service Signature
```python
def wartung_abschliessen(
    gegenstand_repo: GegenstandRepository,
    kategorie_repo: KategorieRepository,
    vormerkung_repo: VormerkungRepository,
    inventarnummer: str,
    ausloeser_rolle: str = "wart",
) -> WartungErgebnis | WartungAblehnung
```

### Algorithm
1. Find Gegenstand by inventarnummer
   - ❌ Not found → return GegenstandNichtGefunden
2. Check: Gegenstand.zustand == WARTUNGSFAELLIG?
   - ❌ No → return NichtWartungsfaellig
3. Get Kategorie
4. Find first offene Vormerkung for Kategorie (sorted by reihenfolge)
5. Determine folgezustand:
   - ✅ Vormerkung exists → RESERVIERT
   - ❌ No Vormerkung → VERFUEGBAR
6. Update Gegenstand atomically:
   - zustand → folgezustand
   - nutzungszaehler → 0
7. Return WartungErgebnis(inventarnummer, zustand, nutzungszaehler, erste_vormerkung_mitglied_id?)

---

## Known Open Questions
1. **Ausleihe-Validierung in UC-01**: Muss UC-01 (gegenstand_ausgeben) prüfen, ob `zustand == RESERVIERT` UND ob Reservierung für dieses Mitglied gilt?
   - Kommentar in ausleihe_service: "die Prüfung... setzt die Vormerkung aus EPIC-E voraus"
   - Decision: **UC-05 fokussiert auf das "Reservieren" selbst. Ausleihe-Validierung für Reservierten Gegenstand ist Future Work.**
   
2. **Response-Format**: Sollen wir die erste Vormerkung (mitglied_id, reihenfolge) im Response mitgeben?
   - Decision: Nein. Der Response zeigt nur den Gegenstand-Zustand. Die Vormerkung wird via GET /vormerkungen abgefragt.
