# Code Review: Leihgut

Date: 2026-08-24

## Findings

### High: missing repository-result guards can cause runtime crashes

`src/leihgut/anwendungskern/ausleihe_service.py::gegenstand_ausgeben` dereferences the category after repository lookup without an immediately visible not-found result path. `src/leihgut/anwendungskern/pruefung_service.py::pruefung_abschliessen` similarly uses the category's maintenance interval after lookup. The return workflow also dereferences the item after `gegenstand_repo.find_by_inventarnummer`. If referential integrity is violated or a fake repository returns `None`, the service can raise `AttributeError` instead of returning a domain error. Add explicit guards or make the repository contract guarantee existence, then test corrupted-reference cases.

### Medium: optional return-service dependencies are used as required

`src/leihgut/anwendungskern/ausleihe_service.py::gegenstand_zuruecknehmen` declares optional `audit_log_repo` and `clock` parameters while using them for audit timestamps. The public signature therefore permits calls that fail at runtime. Make them required or validate the contract at the boundary and add a test for invalid construction.

### Medium: transaction ownership is inconsistent

`src/leihgut/anwendungskern/verlust_service.py::verlust_erfassen` and `audit_retention_service.py::cleanup_audit_log` directly manage SQLite transactions, while other services rely on repository-level persistence. This makes rollback ownership and portability inconsistent. Establish one transaction boundary and test failure paths around `BEGIN`, commit, and rollback.

## Test gaps

* Missing-category checkout and inspection cases.
* Return where the loan references a missing item.
* Invalid optional dependency combinations for return.
* Transaction failure and database-lock paths.
* Concurrent checkout integration coverage beyond the database constraint test.

## Assumptions and limits

The findings assume repository methods may return `None`, as indicated by the application code's not-found patterns. The review did not modify production code or claim that all reported paths are reachable under the current database foreign-key setup.
