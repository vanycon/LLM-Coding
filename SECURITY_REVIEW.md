# Security Review: Leihgut

Date: 2026-08-24

## Findings

### Critical for network exposure: roles are bearer input, not authentication

`src/leihgut/adapters/rest/rollen.py::erfordere_rolle` compares the `X-Rolle` header with allowed strings. `README.adoc` explicitly states that roles are supplied by a header or CLI flag and are not authenticated. Any deployment reachable by an untrusted client must therefore treat the API as unauthorized unless a trusted boundary strips and injects this value or authentication is added. The current design is only consistent with the documented local trusted-process constraint.

### High: audit completeness is not demonstrated

The append-only database triggers protect existing audit rows in `src/leihgut/adapters/persistence/schema.sql`, but the source does not establish that every state-changing use case writes an audit entry. `src/leihgut/anwendungskern/audit_retention_service.py::cleanup_audit_log` is also callable, while its operational scheduling and privileged-action audit semantics are not defined. Add an explicit audit coverage matrix and integration tests before claiming complete accountability.

### Medium: unrestricted request strings have no visible size constraints

The request models in `src/leihgut/adapters/rest/schemas.py` use string fields without visible length limits. The persistence layer uses parameterized SQL, which addresses direct SQL injection, but request-size and storage-abuse controls are not evident. Define limits according to domain rules and test rejection at the HTTP boundary; do not use arbitrary limits without stakeholder agreement.

### Medium: audit data protection and deployment boundary are unspecified

Audit entries include before/after values and deposit-related information through `src/leihgut/domain/audit_log.py`. The code provides role gating but no encryption-at-rest or network security configuration. The acceptable deployment exposure and compensating controls remain an operational/architectural decision.

## Test gaps

* Untrusted or missing role header receives the expected denial.
* Direct network deployment is prevented or authenticated at the deployment boundary.
* Oversized and malformed string inputs are rejected according to agreed limits.
* Every state-changing use case has an audit assertion.
* Retention cleanup failure and authorization behavior are tested.

## Assumptions and limits

The header issue is documented as intentional for a local process; it is a deployment risk, not an accidental bypass under that constraint. No CVSS score is assigned because deployment exposure and trust boundaries are not specified.
