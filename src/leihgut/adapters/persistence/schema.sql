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

-- Ausleihe (UC-01/UC-03/UC-04/UC-06): Zustandswerte nach
-- spec-domain-model.adoc, Abschnitt "Zustandsautomaten" (aktiv →
-- zurueckgegeben → abgeschlossen, bzw. aktiv → abgeschlossen_verloren bei
-- Verlust). kaution_cent ist ein Snapshot des bei der Ausgabe berechneten
-- Betrags (BR-KAT-04) für SI-01; die Kautionsbewegungs-Ledger-Tabelle
-- (Hinterlegung/Abzug/Freigabe) entsteht erst mit EPIC-B (BR-KAU-01/04).
CREATE TABLE IF NOT EXISTS ausleihe (
    ausleihe_id TEXT PRIMARY KEY,
    gegenstand_id TEXT NOT NULL REFERENCES gegenstand (inventarnummer),
    mitglied_id TEXT NOT NULL,
    ausgabedatum TEXT NOT NULL,
    rueckgabefrist TEXT NOT NULL,
    kaution_cent INTEGER NOT NULL,
    verlaengert INTEGER NOT NULL DEFAULT 0,
    zustand TEXT NOT NULL CHECK (
        zustand IN ('aktiv', 'zurueckgegeben', 'abgeschlossen', 'abgeschlossen_verloren')
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

-- Pruefprotokoll (UC-04, BR-RUP-03..06): schliesst eine Ausleihe ab.
-- zielzustand wird hier als tatsaechlich gewaehlter Folgezustand
-- gespeichert (verfuegbar/wartungsfaellig/ausgemustert) -- nicht die vom
-- Wart eingegebene Rohauswahl (die kennt nur verfuegbar/ausgemustert,
-- wartungsfaellig wird abgeleitet, BR-WAR-02).
CREATE TABLE IF NOT EXISTS pruefprotokoll (
    pruefprotokoll_id TEXT PRIMARY KEY,
    ausleihe_id TEXT NOT NULL REFERENCES ausleihe (ausleihe_id),
    kautionsabzug_cent INTEGER NOT NULL CHECK (kautionsabzug_cent >= 0),
    zielzustand TEXT NOT NULL CHECK (
        zielzustand IN ('verfuegbar', 'wartungsfaellig', 'ausgemustert')
    ),
    erstellt_am TEXT NOT NULL
);

-- MaengelEintrag (BR-RUP-05): strukturierte Maengelliste je Gegenstand,
-- ueber alle Pruefprotokolle hinweg. festgestellt_in_pruefprotokoll_id
-- ersetzt das denormalisierte Pruefprotokoll.neueMaengelIds-Feld aus dem
-- Entity-Modell durch eine normale Fremdschluessel-Rueckbeziehung.
CREATE TABLE IF NOT EXISTS maengel_eintrag (
    maengel_id TEXT PRIMARY KEY,
    gegenstand_id TEXT NOT NULL REFERENCES gegenstand (inventarnummer),
    beschreibung TEXT NOT NULL,
    festgestellt_in_pruefprotokoll_id TEXT NOT NULL
        REFERENCES pruefprotokoll (pruefprotokoll_id)
);

-- Kautionsbewegung (BR-KAU-01, BR-KAU-04): 'hinterlegung' ist ein
-- gueltiger, in dieser Codebasis aber (noch) nicht erzeugter Wert -- siehe
-- domain/kautionsbewegung.py.
CREATE TABLE IF NOT EXISTS kautionsbewegung (
    bewegung_id TEXT PRIMARY KEY,
    ausleihe_id TEXT NOT NULL REFERENCES ausleihe (ausleihe_id),
    art TEXT NOT NULL CHECK (art IN ('hinterlegung', 'abzug', 'freigabe')),
    betrag_cent INTEGER NOT NULL CHECK (betrag_cent >= 0),
    zeitstempel TEXT NOT NULL,
    ausloeser TEXT NOT NULL
);
