use std::collections::HashMap;

pub type Cents = u64;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ItemStatus {
    Available,
    OnLoan,
    Reserved,
    InInspection,
    DueForMaintenance,
    Retired,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum LoanStatus {
    Active,
    AwaitingInspection,
    Completed,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum MemberStatus {
    Active,
    Suspended,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum InspectionOutcome {
    Available,
    DueForMaintenance,
    Retired,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DepositType {
    Collection,
    Deduction,
    Release,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ErrorCode {
    CategoryNotFound,
    ItemNotFound,
    MemberNotFound,
    LoanNotFound,
    DuplicateInventoryNumber,
    InvalidValue,
    InvalidState,
    ItemInInspection,
    MaintenanceDue,
    ItemRetired,
    ReservedForOtherMember,
    MemberSuspended,
    LoanLimitReached,
    InstructionRequired,
    LoanOverdue,
    ExtensionAlreadyUsed,
    OpenHold,
    DuplicateReturn,
    DeductionExceedsDeposit,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DomainError {
    pub code: ErrorCode,
    pub message: String,
}
impl DomainError {
    fn new(code: ErrorCode, message: &str) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}
pub type Result<T> = std::result::Result<T, DomainError>;

#[derive(Clone, Debug)]
pub struct Category {
    pub id: String,
    pub name: String,
    pub loan_duration_days: u32,
    pub maintenance_interval_loans: u32,
    pub instruction_required: bool,
}
#[derive(Clone, Debug)]
pub struct Item {
    pub id: String,
    pub inventory_number: String,
    pub category_id: String,
    pub replacement_value_cents: Cents,
    pub status: ItemStatus,
    pub usage_counter: u32,
}
#[derive(Clone, Debug)]
pub struct Member {
    pub id: String,
    pub status: MemberStatus,
}
#[derive(Clone, Debug)]
pub struct Instruction {
    pub member_id: String,
    pub category_id: String,
    pub recorded_at: String,
}
#[derive(Clone, Debug)]
pub struct Loan {
    pub id: String,
    pub item_id: String,
    pub member_id: String,
    pub issued_on: String,
    pub return_deadline: String,
    pub status: LoanStatus,
    pub extension_used: bool,
}
#[derive(Clone, Debug)]
pub struct ReturnRecord {
    pub id: String,
    pub loan_id: String,
    pub returned_at: String,
    pub irregularities: Vec<String>,
}
#[derive(Clone, Debug)]
pub struct InspectionReport {
    pub id: String,
    pub loan_id: String,
    pub inspected_at: String,
    pub outcome: InspectionOutcome,
    pub damage: Vec<String>,
    pub deduction_cents: Cents,
    pub notes: String,
}
#[derive(Clone, Debug)]
pub struct DepositTransaction {
    pub id: String,
    pub loan_id: String,
    pub timestamp: String,
    pub kind: DepositType,
    pub amount_cents: Cents,
    pub trigger: String,
}
#[derive(Clone, Debug)]
pub struct AuditEntry {
    pub id: String,
    pub timestamp: String,
    pub actor: String,
    pub event_type: String,
    pub entity_type: String,
    pub entity_id: String,
    pub details: String,
}
#[derive(Clone, Debug)]
pub struct Hold {
    pub id: String,
    pub member_id: String,
    pub category_id: String,
    pub received_at: String,
    pub open: bool,
}
#[derive(Clone, Debug)]
pub struct Reservation {
    pub id: String,
    pub item_id: String,
    pub member_id: String,
    pub created_at: String,
    pub expires_on: String,
    pub active: bool,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Eligibility {
    pub eligible: bool,
    pub reason: String,
    pub deposit_cents: Option<Cents>,
    pub return_duration_days: Option<u32>,
}

pub fn calculate_deposit(replacement_value_cents: Cents) -> Cents {
    ((replacement_value_cents * 20 + 99) / 100).clamp(500, 10_000)
}

mod service;
pub use service::Service;
fn add_days(date: &str, days: u32) -> String {
    let parts: Vec<u32> = date.split('-').map(|p| p.parse().unwrap_or(0)).collect();
    if parts.len() != 3 {
        return date.into();
    }
    let mut y = parts[0];
    let mut m = parts[1];
    let mut d = parts[2] + days;
    while d > days_in_month(y, m) {
        d -= days_in_month(y, m);
        m += 1;
        if m > 12 {
            m = 1;
            y += 1;
        }
    }
    format!("{y:04}-{m:02}-{d:02}")
}
fn days_in_month(year: u32, month: u32) -> u32 {
    match month {
        2 if year % 4 == 0 => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    }
}

#[cfg(test)]
mod tests;
