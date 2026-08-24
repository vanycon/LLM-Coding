# ATAM Review: Leihgut

Date: 2026-08-24

## Summary

The architecture has useful sensitivity points around the active-loan uniqueness constraint, append-only audit storage, adapter-boundary role checking, and Protocol-based dependency injection. The principal unresolved risks are audit coverage, trusted-header authorization, member-blocking semantics, operational deployment, and unranked quality goals.

## Stakeholders and concerns

* Counter staff: fast, clear checkout and availability decisions.
* Members: reliable availability and FIFO reservations.
* Workshop staff: correct inspection, maintenance, loss, and deposit outcomes.
* Product Owner: error prevention and business success measures.
* Architect/Developer: coherent boundaries, transaction ownership, and evolvability.
* Operations: startup, backup, retention, health, and failure handling.

Evidence: `README.adoc` ("Personas" and "Rahmenbedingungen"), application services under `src/leihgut/anwendungskern/`, and `src/leihgut/adapters/rest/app.py`.

## Quality attribute scenarios

### Functional suitability

Invalid state/value inputs are rejected by application-service validation functions such as `src/leihgut/anwendungskern/ausleihe_service.py::_ausgabe_pruefen`, `pruefung_service.py::_pruefung_pruefen`, and `katalog_service.py::_kategorie_werte_pruefen`.

### Reliability

Two active loans for one item are prevented by `ux_ausleihe_aktiv_je_gegenstand` in `src/leihgut/adapters/persistence/schema.sql`, alongside the SQLite transaction path. The source gives no measured contention or latency target.

### Security

Role checks occur at the REST boundary through `src/leihgut/adapters/rest/rollen.py::erfordere_rolle`, but the role header is explicitly unauthenticated in `README.adoc`. This is a high-sensitivity deployment decision.

### Maintainability and portability

Protocol ports and injected clock/repositories isolate application logic from concrete adapters. Evidence: `src/leihgut/ports/`, `src/leihgut/adapters/system_clock.py::SystemClock`, and `src/leihgut/adapters/rest/app.py::create_app`.

### Audit/compliance

SQLite triggers reject UPDATE and DELETE on audit rows in `src/leihgut/adapters/persistence/schema.sql`; however, complete state-change coverage and retention operations are unresolved.

## Sensitivity points

* Removing the active-loan unique index affects lending reliability.
* Removing audit triggers affects audit integrity.
* Moving role checks away from the REST boundary affects authorization.
* Replacing Protocol ports or the injected clock affects testability and portability.
* Splitting shared `Gegenstand` ownership affects consistency and integration complexity.

## Tradeoff points

* Header roles favor the documented local-process simplicity but sacrifice security outside a trusted boundary.
* SQLite and one local process favor operational simplicity but provide no distributed deployment model.
* Direct reservation coordination favors synchronous simplicity but increases coupling.
* Append-only audit storage favors integrity but creates retention and storage-management obligations.

## Risks and required decisions

1. Define whether every state-changing use case must be audited and test the answer.
2. Define the member-blocking source and semantics.
3. Rank quality goals; the source does not provide a priority order.
4. Define deployment, backup, retention scheduling, health, and recovery targets.
5. Decide whether current cross-capability calls remain a documented modular-monolith boundary or become explicit events/ports.

## Validation gaps

No load, latency, availability, recovery, or capacity measurements are present. No ATAM scenario target should be treated as an SLO until Product Owner and Operations provide it.
