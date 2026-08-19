# UC-01 Erweiterung: RESERVIERT-Gegenstand Handling

## Phase 1: ANALYZE

### Current State
**Problem**: UC-01 prüft nur `zustand == VERFUEGBAR`, lehnt alles andere ab (409).
- ✅ VERFUEGBAR → OK
- ❌ RESERVIERT → 409 GegenstandNichtVerfuegbar
- ❌ IN_PRUEFUNG, AUSGELIEHEN, WARTUNGSFAELLIG, AUSGEMUSTERT → 409

**Aber BR-AUS-01 sagt**:
> "Ein Gegenstand wird nur ausgegeben, wenn er **verfügbar ist oder für das anfragende Mitglied reserviert** ist."

### What Changed Since UC-05?
- UC-05 (Wartung) setzt Gegenstände auf `RESERVIERT` wenn Vormerkung existiert
- Aber UC-01 kann nicht mit RESERVIERT umgehen
- **Result**: Reservierte Gegenstände können nicht ausgegeben werden (semantischer Bug)

### UC-01 Extended Flow
**New Main Success Scenario:**
1. Thekendienst wählt Gegenstand und Mitglied
2. System prüft: Gegenstand verfügbar ODER (reserviert UND für dieses Mitglied)
3. [Rest wie bisher: Sperre, Ausleihlimit, Einweisung]

**New Extension:**
```
2b. Gegenstand reserviert, aber NICHT für dieses Mitglied:
  2b1. System weist die Ausgabe ab (409 GEGENSTAND_NICHT_VERFUEGBAR)
```

### Data Dependencies
To check "reserviert für dieses Mitglied", UC-01 needs:
- Gegenstand.zustand (bereits vorhanden)
- Erste offene Vormerkung für diese Kategorie (via `vormerkung_repo`)
- Vormerkung.mitglied_id (vergleichen mit Parameter mitglied_id)

### Implementation Strategy
1. **No new rejection type** — reuse `GegenstandNichtVerfuegbar` (already 409)
2. **Add new parameter** to `_ausgabe_pruefen()`:
   - `mitglied_id: str` (already have)
   - `erste_vormerkung_mitglied_id: str | None` (new)
3. **Add logic**:
   ```python
   if gegenstand.zustand == GegenstandZustand.RESERVIERT:
       if erste_vormerkung_mitglied_id != mitglied_id:
           return GegenstandNichtVerfuegbar(...)  # not for this member
       # else: OK, fall through
   elif gegenstand.zustand != GegenstandZustand.VERFUEGBAR:
       return GegenstandNichtVerfuegbar(...)
   ```

4. **Update integration** (`gegenstand_ausgeben()`):
   - Load erste offene Vormerkung (if exists)
   - Pass `erste_vormerkung_mitglied_id` to `_ausgabe_pruefen()`

### Test Strategy
**New Service Tests** (in `test_epic_a_ausleihe_kernprozess.py`):
1. Gegenstand VERFUEGBAR → OK (existing, still passes)
2. Gegenstand RESERVIERT, für dieses Mitglied → OK (new)
3. Gegenstand RESERVIERT, für anderes Mitglied → 409 (new)
4. Gegenstand RESERVIERT, keine Vormerkung → Fehler (consistency check)

**New REST Tests** (in `test_epic_a_ausleihe_kernprozess.py`):
- POST /gegenstaende/{inv}/ausgabe mit RESERVIERT-Gegenstand (verschiedene Mitglieder)

### BR Verification
- **BR-AUS-01**: Erfüllt — "verfügbar oder für dieses Mitglied reserviert"
- **BR-VOR-03** (UC-05): Abhängig — UC-05 setzt Reservierung, UC-01 konsumiert sie

### Risk: What Could Break?
1. **Existing tests** rely on specific Gegenstand/Vormerkung state
   - Mitigated: New tests are isolated with fresh data
2. **Race condition**: Vormerkung verschwindet zwischen Check und Ausleihe-Anlage
   - Mitigated: DB CHECK constraint (`ausleihe.zustand` + `gegenstand.zustand`) catches logical inconsistencies
   - Note: This is acceptable (System design allows it per ADR-007)

### Acceptance Criteria (Gherkin)
```gherkin
Feature: UC-01 RESERVIERT-Gegenstand Handling

  Scenario: Verfügbarer Gegenstand wird ausgegeben
    Given Gegenstand "INV-001" ist "verfuegbar"
    When Mitglied "m42" fragt Ausgabe an
    Then wird Ausleihe mit Zustand "aktiv" angelegt

  Scenario: Reservierter Gegenstand für Mitglied wird ausgegeben
    Given Gegenstand "INV-002" ist "reserviert"
    And Vormerkung für Kategorie existiert für Mitglied "m42" mit reihenfolge=1
    When Mitglied "m42" fragt Ausgabe an
    Then wird Ausleihe mit Zustand "aktiv" angelegt
    And Gegenstand-Zustand wechselt zu "ausgeliehen"

  Scenario: Reservierter Gegenstand für anderes Mitglied wird abgelehnt
    Given Gegenstand "INV-003" ist "reserviert"
    And Vormerkung für Kategorie existiert für Mitglied "m99" mit reihenfolge=1
    When Mitglied "m42" (nicht m99) fragt Ausgabe an
    Then wird die Anfrage mit 409 GEGENSTAND_NICHT_VERFUEGBAR abgelehnt
```

### Implementation Effort Estimate
- Modify `_ausgabe_pruefen()`: 30 min
- Modify `gegenstand_ausgeben()`: 30 min
- Add service tests (3-4 Tests): 45 min
- Add REST tests (2-3 Tests): 30 min
- Verify no regressions: 15 min
- **Total: ~2-2.5 hours**

---

## Phase 2: DESIGN (Preview)

### Modified Signature
```python
def _ausgabe_pruefen(
    gegenstand: Gegenstand,
    kategorie: Kategorie,
    mitglied_id: str,
    mitglied_gesperrt: bool,
    offene_ausleihen_anzahl: int,
    einweisung_gueltig: bool,
    erste_vormerkung_mitglied_id: str | None,  # NEW
) -> AusgabeAblehnung | None
```

### Decision Tree
```
gegenstand.zustand == VERFUEGBAR?
  ✅ YES → check rest (sperre, limit, einweisung)
  ❌ NO:
    zustand == RESERVIERT?
      ✅ YES → erste_vormerkung_mitglied_id == mitglied_id?
        ✅ YES → check rest (sperre, limit, einweisung)
        ❌ NO → REJECT (GegenstandNichtVerfuegbar)
      ❌ NO → REJECT (GegenstandNichtVerfuegbar)
```

### Call Site Changes
```python
def gegenstand_ausgeben(...):
    # Before: just pass gegenstand to _ausgabe_pruefen()
    
    # After:
    erste_vormerkung = None
    if gegenstand.zustand == GegenstandZustand.RESERVIERT:
        erste_vormerkung = vormerkung_repo.find_offene_je_kategorie_sortiert_nach_reihenfolge(
            gegenstand.kategorie_id
        )
        if erste_vormerkung:
            erste_vormerkung_mitglied_id = erste_vormerkung[0].mitglied_id
        else:
            erste_vormerkung_mitglied_id = None
    else:
        erste_vormerkung_mitglied_id = None
    
    ablehnung = _ausgabe_pruefen(
        ...,
        erste_vormerkung_mitglied_id=erste_vormerkung_mitglied_id,
    )
```

---

## Known Unknowns / Questions
1. **Should UC-01 clear Vormerkung after Ausleihe?**
   - No. Per UC-05 spec, Vormerkung bleibt. Mitglied muss es explizit absagen.
   - Spec (UC-11): "Vormerkung verfällt nach 7 Tagen" (BR-VOR-04, nicht implementiert)

2. **What if Vormerkungs-Mitglied ist gesperrt?**
   - UC-01 prüft erst Verfügbarkeit, dann Sperre
   - Wenn Mitglied gesperrt: auch reservierter Gegenstand kann nicht ausgegeben werden
   - Correct per BR-AUS-03 ("gesperrtes Mitglied erhält keine Ausgabe")
