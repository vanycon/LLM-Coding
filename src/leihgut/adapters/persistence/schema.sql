-- Schema Leihgut (Skeleton-01, wird in EPIC-D/A/B/E/... erweitert).
--
-- Enthält bereits die zwei DB-erzwungenen Mechanismen aus den ATAM-Nachträgen,
-- damit sie von Anfang an im Schema stehen statt später nachgezogen zu werden:
--   * ADR-007: partieller Unique-Index gegen zwei gleichzeitig aktive
--     Ausleihen desselben Gegenstands (TOCTOU-Schutz).
--   * ADR-009: Trigger, die UPDATE/DELETE auf dem Audit-Log zurückweisen.
--
-- Siehe src/docs/arc42/chapters/09_architecture_decisions.adoc.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS kategorie (
    kategorie_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    leihdauer_tage INTEGER NOT NULL,
    wartungsintervall INTEGER,
    einweisungspflichtig INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS gegenstand (
    inventarnummer TEXT PRIMARY KEY,
    kategorie_id TEXT NOT NULL REFERENCES kategorie (kategorie_id),
    wiederbeschaffungswert_cent INTEGER NOT NULL CHECK (wiederbeschaffungswert_cent > 0),
    nutzungszaehler INTEGER NOT NULL DEFAULT 0,
    zustand TEXT NOT NULL CHECK (
        zustand IN (
            'verfuegbar', 'ausgeliehen', 'in_pruefung',
            'wartungsfaellig', 'reserviert', 'ausgemustert'
        )
    )
);

-- Ausschnitt für Skeleton-01 / spätere ADR-007-Absicherung (EPIC-A).
CREATE TABLE IF NOT EXISTS ausleihe (
    ausleihe_id TEXT PRIMARY KEY,
    gegenstand_id TEXT NOT NULL REFERENCES gegenstand (inventarnummer),
    mitglied_id TEXT NOT NULL,
    ausgabedatum TEXT NOT NULL,
    rueckgabefrist TEXT NOT NULL,
    verlaengert INTEGER NOT NULL DEFAULT 0,
    zustand TEXT NOT NULL CHECK (
        zustand IN ('aktiv', 'zurueckgenommen', 'in_pruefung', 'abgeschlossen')
    ),
    rueckgabe_auffaelligkeiten TEXT
);

-- ADR-007: höchstens eine aktive Ausleihe je Gegenstand, DB-erzwungen
-- unabhängig von der Anwendungslogik (zweite Schranke neben BEGIN IMMEDIATE).
CREATE UNIQUE INDEX IF NOT EXISTS ux_ausleihe_aktiv_je_gegenstand
    ON ausleihe (gegenstand_id)
    WHERE zustand = 'aktiv';

-- Einweisung (UC-07/UC-08): mitglied_id bleibt wie ausleihe.mitglied_id ein
-- reines TEXT-Feld ohne FK, weil Mitglieder außerhalb dieses Systems verwaltet
-- werden (spec-domain-model.adoc: Mitglied hat nur eine mitgliedId und ein
-- abgeleitetes gesperrt-Flag, kein eigenes Anlegen-UC).
CREATE TABLE IF NOT EXISTS einweisung (
    einweisung_id TEXT PRIMARY KEY,
    mitglied_id TEXT NOT NULL,
    kategorie_id TEXT NOT NULL REFERENCES kategorie (kategorie_id),
    erstellt_am TEXT NOT NULL,
    widerrufen_am TEXT
);

-- BR-EIN-01: höchstens eine gültige (nicht widerrufene) Einweisung je
-- Mitglied/Kategorie — analog zu ADR-007 als zweite, DB-erzwungene Schranke
-- neben der Prüfung im Anwendungsdienst.
CREATE UNIQUE INDEX IF NOT EXISTS ux_einweisung_gueltig_je_mitglied_kategorie
    ON einweisung (mitglied_id, kategorie_id)
    WHERE widerrufen_am IS NULL;

-- Audit-Log: append-only, Schreibvorgänge laufen in derselben Transaktion
-- wie die Fachänderung (04_solution_strategy.adoc, Nachvollziehbarkeit).
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    zeitstempel TEXT NOT NULL,
    aggregat TEXT NOT NULL,
    aggregat_id TEXT NOT NULL,
    ereignisart TEXT NOT NULL,
    rolle TEXT NOT NULL,
    werte_vorher TEXT,
    werte_nachher TEXT
);

-- ADR-009: technisch erzwungene Unveränderlichkeit. Schützt nur vor
-- Manipulation über SQL, nicht vor Zugriff unterhalb von SQLite (R-002,
-- 11_technical_risks.adoc).
CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log ist unveraenderlich (ADR-009): UPDATE nicht erlaubt');
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log ist unveraenderlich (ADR-009): DELETE nicht erlaubt');
END;
