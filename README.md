# Leihgut

The project currently contains the release specification and the first Rust domain slice.

Run the domain tests with:

```text
cargo test
```

The dependency-ordered implementation backlog is in [BACKLOG.adoc](BACKLOG.adoc). The initial SQLite schema is in `migrations/0001_initial.sql`.

Rust code follows a maintainability rule: keep crate roots thin and separate production modules from tests where practical. Keep source files at or below 500 lines as a soft guideline; files above that size receive a split review, with documented exceptions for genuinely cohesive modules.