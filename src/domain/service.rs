use super::*;

#[derive(Default)]
pub struct Service {
    pub categories: HashMap<String, Category>,
    pub items: HashMap<String, Item>,
    pub members: HashMap<String, Member>,
    pub instructions: Vec<Instruction>,
    pub loans: HashMap<String, Loan>,
    pub returns: HashMap<String, ReturnRecord>,
    pub inspections: HashMap<String, InspectionReport>,
    pub deposits: Vec<DepositTransaction>,
    pub audits: Vec<AuditEntry>,
    pub holds: Vec<Hold>,
    pub reservations: Vec<Reservation>,
    next_id: u64,
}
impl Service {
    pub fn new() -> Self {
        Self::default()
    }
    fn id(&mut self, prefix: &str) -> String {
        self.next_id += 1;
        format!("{prefix}-{}", self.next_id)
    }
    fn audit(
        &mut self,
        actor: &str,
        event: &str,
        entity_type: &str,
        entity_id: &str,
        details: &str,
        now: &str,
    ) {
        let id = self.id("AUD");
        self.audits.push(AuditEntry {
            id,
            timestamp: now.into(),
            actor: actor.into(),
            event_type: event.into(),
            entity_type: entity_type.into(),
            entity_id: entity_id.into(),
            details: details.into(),
        });
    }
    pub fn add_category(&mut self, category: Category) -> Result<()> {
        if category.loan_duration_days == 0 || category.maintenance_interval_loans == 0 {
            return Err(DomainError::new(
                ErrorCode::InvalidValue,
                "durations must be positive",
            ));
        }
        if self.categories.contains_key(&category.id) {
            return Err(DomainError::new(
                ErrorCode::InvalidValue,
                "duplicate category",
            ));
        }
        self.categories.insert(category.id.clone(), category);
        Ok(())
    }
    pub fn add_item(&mut self, item: Item) -> Result<()> {
        if !self.categories.contains_key(&item.category_id) || item.replacement_value_cents == 0 {
            return Err(DomainError::new(
                ErrorCode::InvalidValue,
                "invalid item category or value",
            ));
        }
        if self
            .items
            .values()
            .any(|i| i.inventory_number == item.inventory_number)
        {
            return Err(DomainError::new(
                ErrorCode::DuplicateInventoryNumber,
                "inventory number is not unique",
            ));
        }
        self.items.insert(item.id.clone(), item);
        Ok(())
    }
    pub fn add_member(&mut self, member: Member) {
        self.members.insert(member.id.clone(), member);
    }
    pub fn record_instruction(
        &mut self,
        member_id: &str,
        category_id: &str,
        recorded_at: &str,
    ) -> Result<()> {
        if !self.members.contains_key(member_id) || !self.categories.contains_key(category_id) {
            return Err(DomainError::new(
                ErrorCode::InvalidValue,
                "unknown member or category",
            ));
        }
        self.instructions
            .retain(|i| !(i.member_id == member_id && i.category_id == category_id));
        self.instructions.push(Instruction {
            member_id: member_id.into(),
            category_id: category_id.into(),
            recorded_at: recorded_at.into(),
        });
        Ok(())
    }
    fn active_loans(&self, member_id: &str) -> usize {
        self.loans
            .values()
            .filter(|l| l.member_id == member_id && l.status != LoanStatus::Completed)
            .count()
    }
    fn overdue(&self, member_id: &str, today: &str) -> bool {
        self.loans.values().any(|l| {
            l.member_id == member_id
                && l.status != LoanStatus::Completed
                && l.return_deadline.as_str() < today
        })
    }
    fn eligible_reason(&self, item_id: &str, member_id: &str, today: &str) -> Result<Eligibility> {
        let item = self
            .items
            .get(item_id)
            .ok_or_else(|| DomainError::new(ErrorCode::ItemNotFound, "item not found"))?;
        let member = self
            .members
            .get(member_id)
            .ok_or_else(|| DomainError::new(ErrorCode::MemberNotFound, "member not found"))?;
        let category = self
            .categories
            .get(&item.category_id)
            .ok_or_else(|| DomainError::new(ErrorCode::CategoryNotFound, "category not found"))?;
        let reject = |_code: ErrorCode, reason: &str| {
            Ok(Eligibility {
                eligible: false,
                reason: reason.into(),
                deposit_cents: None,
                return_duration_days: None,
            })
        };
        if item.status == ItemStatus::InInspection {
            return reject(ErrorCode::ItemInInspection, "ITEM_IN_INSPECTION");
        }
        if item.status == ItemStatus::DueForMaintenance {
            return reject(ErrorCode::MaintenanceDue, "MAINTENANCE_DUE");
        }
        if item.status == ItemStatus::Retired {
            return reject(ErrorCode::ItemRetired, "ITEM_RETIRED");
        }
        if item.status == ItemStatus::Reserved
            && !self
                .reservations
                .iter()
                .any(|r| r.item_id == item_id && r.member_id == member_id && r.active)
        {
            return reject(
                ErrorCode::ReservedForOtherMember,
                "RESERVED_FOR_OTHER_MEMBER",
            );
        }
        if member.status == MemberStatus::Suspended || self.overdue(member_id, today) {
            return reject(ErrorCode::MemberSuspended, "MEMBER_SUSPENDED");
        }
        if self.active_loans(member_id) >= 3 {
            return reject(ErrorCode::LoanLimitReached, "LOAN_LIMIT_REACHED");
        }
        if category.instruction_required
            && !self
                .instructions
                .iter()
                .any(|i| i.member_id == member_id && i.category_id == item.category_id)
        {
            return reject(ErrorCode::InstructionRequired, "INSTRUCTION_REQUIRED");
        }
        Ok(Eligibility {
            eligible: true,
            reason: "ELIGIBLE".into(),
            deposit_cents: Some(calculate_deposit(item.replacement_value_cents)),
            return_duration_days: Some(category.loan_duration_days),
        })
    }
    pub fn check_eligibility(
        &self,
        item_id: &str,
        member_id: &str,
        today: &str,
    ) -> Result<Eligibility> {
        self.eligible_reason(item_id, member_id, today)
    }
    pub fn issue(
        &mut self,
        item_id: &str,
        member_id: &str,
        today: &str,
        actor: &str,
    ) -> Result<Loan> {
        let decision = self.eligible_reason(item_id, member_id, today)?;
        if !decision.eligible {
            return Err(DomainError::new(ErrorCode::InvalidState, &decision.reason));
        }
        let item = self.items.get(item_id).unwrap().clone();
        let category = self.categories.get(&item.category_id).unwrap().clone();
        let id = self.id("L");
        let deadline = add_days(today, category.loan_duration_days);
        let loan = Loan {
            id: id.clone(),
            item_id: item_id.into(),
            member_id: member_id.into(),
            issued_on: today.into(),
            return_deadline: deadline,
            status: LoanStatus::Active,
            extension_used: false,
        };
        self.loans.insert(id.clone(), loan.clone());
        self.items.get_mut(item_id).unwrap().status = ItemStatus::OnLoan;
        if let Some(r) = self
            .reservations
            .iter_mut()
            .find(|r| r.item_id == item_id && r.member_id == member_id && r.active)
        {
            r.active = false;
        }
        let dep = calculate_deposit(item.replacement_value_cents);
        let did = self.id("DEP");
        self.deposits.push(DepositTransaction {
            id: did,
            loan_id: id.clone(),
            timestamp: today.into(),
            kind: DepositType::Collection,
            amount_cents: dep,
            trigger: "ISSUE".into(),
        });
        self.audit(actor, "ISSUED", "LOAN", &id, "item issued", today);
        Ok(loan)
    }
    pub fn extend(&mut self, loan_id: &str, today: &str, actor: &str) -> Result<Loan> {
        let old = self
            .loans
            .get(loan_id)
            .ok_or_else(|| DomainError::new(ErrorCode::LoanNotFound, "loan not found"))?
            .clone();
        if old.status != LoanStatus::Active {
            return Err(DomainError::new(
                ErrorCode::InvalidState,
                "loan is not active",
            ));
        }
        if old.extension_used {
            return Err(DomainError::new(
                ErrorCode::ExtensionAlreadyUsed,
                "extension already used",
            ));
        }
        if old.return_deadline.as_str() < today {
            return Err(DomainError::new(ErrorCode::LoanOverdue, "loan is overdue"));
        }
        let item = self.items.get(&old.item_id).unwrap();
        if self
            .holds
            .iter()
            .any(|h| h.category_id == item.category_id && h.open)
        {
            return Err(DomainError::new(
                ErrorCode::OpenHold,
                "category has an open hold",
            ));
        }
        let days = self
            .categories
            .get(&item.category_id)
            .unwrap()
            .loan_duration_days;
        let mut updated = old.clone();
        updated.return_deadline = add_days(&old.return_deadline, days);
        updated.extension_used = true;
        self.loans.insert(loan_id.into(), updated.clone());
        self.audit(
            actor,
            "EXTENDED",
            "LOAN",
            loan_id,
            &format!(
                "deadline {} -> {}",
                old.return_deadline, updated.return_deadline
            ),
            today,
        );
        Ok(updated)
    }
    pub fn return_item(
        &mut self,
        loan_id: &str,
        returned_at: &str,
        irregularities: Vec<String>,
        actor: &str,
    ) -> Result<ReturnRecord> {
        let loan = self
            .loans
            .get(loan_id)
            .ok_or_else(|| DomainError::new(ErrorCode::LoanNotFound, "loan not found"))?
            .clone();
        if loan.status != LoanStatus::Active || self.returns.contains_key(loan_id) {
            return Err(DomainError::new(
                ErrorCode::DuplicateReturn,
                "loan cannot be returned",
            ));
        }
        let item_id = loan.item_id.clone();
        let record = ReturnRecord {
            id: self.id("RET"),
            loan_id: loan_id.into(),
            returned_at: returned_at.into(),
            irregularities,
        };
        self.returns.insert(loan_id.into(), record.clone());
        self.loans.get_mut(loan_id).unwrap().status = LoanStatus::AwaitingInspection;
        self.items.get_mut(&item_id).unwrap().status = ItemStatus::InInspection;
        self.audit(
            actor,
            "RETURNED",
            "LOAN",
            loan_id,
            "awaiting inspection",
            returned_at,
        );
        Ok(record)
    }
    pub fn inspect(
        &mut self,
        loan_id: &str,
        outcome: InspectionOutcome,
        damage: Vec<String>,
        deduction: Cents,
        notes: String,
        now: &str,
        actor: &str,
    ) -> Result<InspectionReport> {
        let loan = self
            .loans
            .get(loan_id)
            .ok_or_else(|| DomainError::new(ErrorCode::LoanNotFound, "loan not found"))?
            .clone();
        if loan.status != LoanStatus::AwaitingInspection || self.inspections.contains_key(loan_id) {
            return Err(DomainError::new(
                ErrorCode::InvalidState,
                "loan is not awaiting inspection",
            ));
        }
        let collected: Cents = self
            .deposits
            .iter()
            .filter(|d| d.loan_id == loan_id && d.kind == DepositType::Collection)
            .map(|d| d.amount_cents)
            .sum();
        if deduction > collected {
            return Err(DomainError::new(
                ErrorCode::DeductionExceedsDeposit,
                "deduction exceeds deposit",
            ));
        }
        let report = InspectionReport {
            id: self.id("IR"),
            loan_id: loan_id.into(),
            inspected_at: now.into(),
            outcome: outcome.clone(),
            damage,
            deduction_cents: deduction,
            notes,
        };
        self.inspections.insert(loan_id.into(), report.clone());
        self.loans.get_mut(loan_id).unwrap().status = LoanStatus::Completed;
        let category = self
            .categories
            .get(&self.items[&loan.item_id].category_id)
            .unwrap();
        let item = self.items.get_mut(&loan.item_id).unwrap();
        item.usage_counter += 1;
        item.status = match outcome {
            InspectionOutcome::Available
                if item.usage_counter >= category.maintenance_interval_loans =>
            {
                ItemStatus::DueForMaintenance
            }
            InspectionOutcome::Available => ItemStatus::Available,
            InspectionOutcome::DueForMaintenance => ItemStatus::DueForMaintenance,
            InspectionOutcome::Retired => ItemStatus::Retired,
        };
        if deduction > 0 {
            let id = self.id("DEP");
            self.deposits.push(DepositTransaction {
                id,
                loan_id: loan_id.into(),
                timestamp: now.into(),
                kind: DepositType::Deduction,
                amount_cents: deduction,
                trigger: "INSPECTION".into(),
            });
        }
        let release = if matches!(outcome, InspectionOutcome::Retired) {
            0
        } else {
            collected - deduction
        };
        if release > 0 {
            let id = self.id("DEP");
            self.deposits.push(DepositTransaction {
                id,
                loan_id: loan_id.into(),
                timestamp: now.into(),
                kind: DepositType::Release,
                amount_cents: release,
                trigger: "INSPECTION".into(),
            });
        }
        self.audit(
            actor,
            "INSPECTED",
            "LOAN",
            loan_id,
            "inspection completed",
            now,
        );
        Ok(report)
    }
    pub fn create_hold(
        &mut self,
        member_id: &str,
        category_id: &str,
        received_at: &str,
        actor: &str,
    ) -> Result<Hold> {
        if !self.members.contains_key(member_id) || !self.categories.contains_key(category_id) {
            return Err(DomainError::new(
                ErrorCode::InvalidValue,
                "unknown member or category",
            ));
        }
        let hold = Hold {
            id: self.id("H"),
            member_id: member_id.into(),
            category_id: category_id.into(),
            received_at: received_at.into(),
            open: true,
        };
        self.holds.push(hold.clone());
        self.audit(
            actor,
            "HOLD_CREATED",
            "HOLD",
            &hold.id,
            "hold opened",
            received_at,
        );
        Ok(hold)
    }
    pub fn allocate_reservation(
        &mut self,
        category_id: &str,
        item_id: &str,
        today: &str,
        actor: &str,
    ) -> Result<Option<Reservation>> {
        let item = self
            .items
            .get(item_id)
            .ok_or_else(|| DomainError::new(ErrorCode::ItemNotFound, "item not found"))?;
        if item.category_id != category_id {
            return Err(DomainError::new(
                ErrorCode::InvalidValue,
                "item category mismatch",
            ));
        }
        if item.status != ItemStatus::Available {
            return Ok(None);
        }
        let mut candidates: Vec<Hold> = self
            .holds
            .iter()
            .filter(|h| h.category_id == category_id && h.open)
            .cloned()
            .collect();
        candidates.sort_by(|left, right| {
            left.received_at
                .cmp(&right.received_at)
                .then(left.id.cmp(&right.id))
        });
        let hold = candidates.into_iter().find(|h| {
            self.members
                .get(&h.member_id)
                .is_some_and(|m| m.status == MemberStatus::Active)
                && !self.overdue(&h.member_id, today)
        });
        let Some(hold) = hold else {
            return Ok(None);
        };
        let reservation = Reservation {
            id: self.id("RES"),
            item_id: item_id.into(),
            member_id: hold.member_id.clone(),
            created_at: today.into(),
            expires_on: add_days(today, 3),
            active: true,
        };
        self.reservations.push(reservation.clone());
        self.items.get_mut(item_id).unwrap().status = ItemStatus::Reserved;
        self.holds
            .iter_mut()
            .find(|h| h.id == hold.id)
            .unwrap()
            .open = false;
        self.audit(
            actor,
            "RESERVATION_ALLOCATED",
            "RESERVATION",
            &reservation.id,
            "hold allocated",
            today,
        );
        Ok(Some(reservation))
    }
    pub fn expire_reservations(&mut self, today: &str, actor: &str) -> usize {
        let expired: Vec<String> = self
            .reservations
            .iter()
            .filter(|r| r.active && r.expires_on.as_str() <= today)
            .map(|r| r.id.clone())
            .collect();
        let mut count = 0;
        for reservation_id in expired {
            let Some(index) = self
                .reservations
                .iter()
                .position(|r| r.id == reservation_id)
            else {
                continue;
            };
            let item_id = self.reservations[index].item_id.clone();
            self.reservations[index].active = false;
            if let Some(item) = self.items.get_mut(&item_id) {
                item.status = ItemStatus::Available;
            }
            self.audit(
                actor,
                "RESERVATION_EXPIRED",
                "RESERVATION",
                &reservation_id,
                "reservation expired",
                today,
            );
            count += 1;
        }
        count
    }
    pub fn complete_maintenance(
        &mut self,
        item_id: &str,
        completed_at: &str,
        actor: &str,
    ) -> Result<()> {
        let item = self
            .items
            .get_mut(item_id)
            .ok_or_else(|| DomainError::new(ErrorCode::ItemNotFound, "item not found"))?;
        if item.status != ItemStatus::DueForMaintenance {
            return Err(DomainError::new(
                ErrorCode::InvalidState,
                "item is not due for maintenance",
            ));
        }
        item.status = ItemStatus::Available;
        item.usage_counter = 0;
        self.audit(
            actor,
            "MAINTENANCE_COMPLETED",
            "ITEM",
            item_id,
            "maintenance complete",
            completed_at,
        );
        Ok(())
    }
}
