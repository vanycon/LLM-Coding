PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    category_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    loan_duration_days INTEGER NOT NULL CHECK (loan_duration_days > 0),
    maintenance_interval_loans INTEGER NOT NULL CHECK (maintenance_interval_loans > 0),
    instruction_required INTEGER NOT NULL CHECK (instruction_required IN (0, 1))
);
CREATE TABLE IF NOT EXISTS items (
    item_id TEXT PRIMARY KEY,
    inventory_number TEXT NOT NULL UNIQUE,
    category_id TEXT NOT NULL REFERENCES categories(category_id),
    replacement_value_cents INTEGER NOT NULL CHECK (replacement_value_cents > 0),
    status TEXT NOT NULL,
    usage_counter INTEGER NOT NULL CHECK (usage_counter >= 0)
);
CREATE TABLE IF NOT EXISTS members (
    member_id TEXT PRIMARY KEY,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS instructions (
    member_id TEXT NOT NULL REFERENCES members(member_id),
    category_id TEXT NOT NULL REFERENCES categories(category_id),
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (member_id, category_id)
);
CREATE TABLE IF NOT EXISTS loans (
    loan_id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL UNIQUE REFERENCES items(item_id),
    member_id TEXT NOT NULL REFERENCES members(member_id),
    issued_at TEXT NOT NULL,
    return_deadline TEXT NOT NULL,
    status TEXT NOT NULL,
    extension_used INTEGER NOT NULL CHECK (extension_used IN (0, 1))
);
CREATE TABLE IF NOT EXISTS returns (
    return_id TEXT PRIMARY KEY,
    loan_id TEXT NOT NULL UNIQUE REFERENCES loans(loan_id),
    returned_at TEXT NOT NULL,
    irregularities TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inspection_reports (
    inspection_report_id TEXT PRIMARY KEY,
    loan_id TEXT NOT NULL UNIQUE REFERENCES loans(loan_id),
    inspected_at TEXT NOT NULL,
    outcome TEXT NOT NULL,
    damage TEXT NOT NULL,
    deduction_cents INTEGER NOT NULL CHECK (deduction_cents >= 0),
    notes TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deposit_transactions (
    transaction_id TEXT PRIMARY KEY,
    loan_id TEXT NOT NULL REFERENCES loans(loan_id),
    timestamp TEXT NOT NULL,
    type TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    trigger TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS holds (
    hold_id TEXT PRIMARY KEY,
    member_id TEXT NOT NULL REFERENCES members(member_id),
    category_id TEXT NOT NULL REFERENCES categories(category_id),
    received_at TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reservations (
    reservation_id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL UNIQUE REFERENCES items(item_id),
    member_id TEXT NOT NULL REFERENCES members(member_id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_entries (
    audit_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    details TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_holds_queue ON holds(category_id, received_at, hold_id);
CREATE INDEX IF NOT EXISTS idx_deposits_loan ON deposit_transactions(loan_id);
CREATE INDEX IF NOT EXISTS idx_audits_entity ON audit_entries(entity_type, entity_id, timestamp);
