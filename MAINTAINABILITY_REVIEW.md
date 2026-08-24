# Maintainability Review: Leihgut

Date: 2026-08-24

## Findings

### High: application services and persistence adapters have inconsistent transaction boundaries

`src/leihgut/anwendungskern/verlust_service.py::verlust_erfassen` and `src/leihgut/anwendungskern/audit_retention_service.py::cleanup_audit_log` know about `sqlite3` and manage transactions directly, while other application services use repository ports. This weakens the port/adapters boundary and makes a future persistence change require service changes. Introduce a documented unit-of-work/transaction port or standardize repository transaction ownership.

### Medium: REST error mapping is repetitive and fragile

`src/leihgut/adapters/rest/app.py` contains multiple service-specific rejection-to-HTTP mapping functions. Repeated mapping structure increases the number of places that must change when the error response contract changes. Centralize the common mapping while preserving service-specific error tables.

### Medium: domain/application error types are duplicated

Several application services define similarly named errors such as `GegenstandNichtGefunden`, requiring aliases in `src/leihgut/adapters/rest/app.py`. A shared error taxonomy would reduce adapter complexity, provided ownership and public semantics are agreed first.

### Medium: cross-capability coordination is an implicit dependency

Lending/return and maintenance workflows call reservation logic directly, and `Gegenstand` is changed by multiple workflows. The current modular-monolith approach is workable, but the boundary and ownership are not expressed as a protocol or event contract. Document the dependency and add interaction tests before splitting modules or services.

### Medium: dependency and documentation drift reduce reproducibility

`pyproject.toml` declares version ranges and Typer, while the README describes a CLI whose entry point is not evident in `src/leihgut/`. Phase 1 also references documentation paths that are not present in the workspace. Define supported commands/versions and keep references synchronized.

## Test gaps

* Contract tests for the generic REST error mapping.
* Unit tests for pure state-transition and FIFO helpers.
* Failure-path tests for each transaction-owning service.
* Architecture checks preventing application services from importing SQLite directly.
* A test or build check for the documented CLI entry point and dependency set.

## Assumptions and limits

This review treats the current direct calls as maintainability risks, not defects that require immediate decomposition. No performance or test-count claims are made without repository measurement.
