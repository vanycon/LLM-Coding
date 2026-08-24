use super::*;

fn service() -> Service {
    let mut s = Service::new();
    s.add_category(Category {
        id: "tools".into(),
        name: "Tools".into(),
        loan_duration_days: 14,
        maintenance_interval_loans: 10,
        instruction_required: true,
    })
    .unwrap();
    s.add_item(Item {
        id: "item".into(),
        inventory_number: "INV-1".into(),
        category_id: "tools".into(),
        replacement_value_cents: 25_000,
        status: ItemStatus::Available,
        usage_counter: 0,
    })
    .unwrap();
    s.add_member(Member {
        id: "member".into(),
        status: MemberStatus::Active,
    });
    s.record_instruction("member", "tools", "2026-01-01")
        .unwrap();
    s
}

#[test]
fn issue_0006_catalog_and_0013_deposit() {
    let mut s = service();
    let loan = s.issue("item", "member", "2026-08-24", "clerk").unwrap();
    assert_eq!(loan.return_deadline, "2026-09-07");
    assert_eq!(s.deposits[0].amount_cents, 5000);
}

#[test]
fn issue_0008_is_read_only_and_reasons() {
    let s = service();
    let before = (s.loans.len(), s.deposits.len(), s.audits.len());
    let result = s.check_eligibility("item", "member", "2026-08-24").unwrap();
    assert!(result.eligible);
    assert_eq!(before, (s.loans.len(), s.deposits.len(), s.audits.len()));
}

#[test]
fn issue_0010_0011_0012_lifecycle() {
    let mut s = service();
    let loan = s.issue("item", "member", "2026-08-24", "clerk").unwrap();
    let extended = s.extend(&loan.id, "2026-08-25", "clerk").unwrap();
    assert_eq!(extended.return_deadline, "2026-09-21");
    s.return_item(
        &loan.id,
        "2026-09-01T10:00:00Z",
        vec!["CRACKED_HOUSING".into()],
        "clerk",
    )
    .unwrap();
    let report = s
        .inspect(
            &loan.id,
            InspectionOutcome::Available,
            vec![],
            0,
            "ok".into(),
            "2026-09-02",
            "tech",
        )
        .unwrap();
    assert_eq!(report.outcome, InspectionOutcome::Available);
    assert_eq!(s.loans[&loan.id].status, LoanStatus::Completed);
    assert_eq!(s.items["item"].usage_counter, 1);
}

#[test]
fn issue_0014_retired_retains_deposit() {
    let mut s = service();
    let loan = s.issue("item", "member", "2026-08-24", "clerk").unwrap();
    s.return_item(&loan.id, "2026-09-01", vec![], "clerk")
        .unwrap();
    s.inspect(
        &loan.id,
        InspectionOutcome::Retired,
        vec![],
        5000,
        "lost".into(),
        "2026-09-02",
        "tech",
    )
    .unwrap();
    assert_eq!(s.items["item"].status, ItemStatus::Retired);
    assert_eq!(
        s.deposits
            .iter()
            .map(|d| if d.kind == DepositType::Release {
                d.amount_cents
            } else {
                0
            })
            .sum::<u64>(),
        0
    );
}

#[test]
fn issue_0015_allocates_in_queue_order_and_expires() {
    let mut s = service();
    s.add_member(Member {
        id: "second".into(),
        status: MemberStatus::Active,
    });
    s.create_hold("member", "tools", "2026-08-24T09:00:00Z", "member")
        .unwrap();
    s.create_hold("second", "tools", "2026-08-24T10:00:00Z", "member")
        .unwrap();
    let reservation = s
        .allocate_reservation("tools", "item", "2026-08-24", "clerk")
        .unwrap()
        .unwrap();
    assert_eq!(reservation.member_id, "member");
    assert_eq!(reservation.expires_on, "2026-08-27");
    assert_eq!(s.expire_reservations("2026-08-27", "clerk"), 1);
    assert_eq!(s.items["item"].status, ItemStatus::Available);
}

#[test]
fn issue_0015_skips_suspended_hold_without_reordering() {
    let mut s = service();
    s.members.get_mut("member").unwrap().status = MemberStatus::Suspended;
    s.add_member(Member {
        id: "second".into(),
        status: MemberStatus::Active,
    });
    s.create_hold("member", "tools", "2026-08-24T09:00:00Z", "member")
        .unwrap();
    s.create_hold("second", "tools", "2026-08-24T10:00:00Z", "member")
        .unwrap();
    let reservation = s
        .allocate_reservation("tools", "item", "2026-08-24", "clerk")
        .unwrap()
        .unwrap();
    assert_eq!(reservation.member_id, "second");
    assert!(
        s.holds
            .iter()
            .find(|h| h.member_id == "member")
            .unwrap()
            .open
    );
}
