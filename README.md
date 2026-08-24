# Leihgut

The project currently contains the release specification and the first Rust domain slice.

Run the domain tests with:

```text
cargo test
```

The dependency-ordered implementation backlog is in [BACKLOG.adoc](BACKLOG.adoc). The initial SQLite schema is in `migrations/0001_initial.sql`.

Rust code follows a maintainability rule: keep crate roots thin and separate production modules from tests where practical. Keep source files at or below 500 lines as a soft guideline; files above that size receive a split review, with documented exceptions for genuinely cohesive modules.

## Prompt History

- Please translate this file into `prd_en.adoc`
- Look ath `prd.adoc` and ask me questions using the socratic method until no unclear requirements are left.
- Create a specification based on the `prd.adoc`. Use sub-agents for each use case.
- Create an architecture based on the specs and document it with __arc42__.
- We are working on this project without __GitHub Issues__. Create Issues as text files instead and follow this...
- Please create __epics and stories__ as issues for the __use cases__.
The __epics and stories__ should satisfy the __complete specification__ with __MECE__.
- Are these enough issues?
- What __technologies__ would you suggest given the project specification and given that the team is experienced with Rust?
- Given that define a __devcontainer__. Make sure it covers Rust and make sure it can support the database technology chosen.
If necessary __document the decision__ which technology we use.
- `/compact`
- Go through all issues and create a __sensible backlog__ considering dependencies and solve the issues using __TDD__ in a style you prefer or that seems most sensible. Use subagents when it makes sense. Try to do this without needing to ask for any permissions. Do NOT use the internet or any non-local sources.
- Now there seem to be a lot of file artifacts, e.g. under target - please create a designated .gitignore
- Please add another criteria that a useful file structure should be maintained.
Meaning no super long source files.
Apply best practises and if contained split source and tests in a rust way.
- I see that there are still some large files over 100 might be ok, but more than 500 could be avoided - establish a soft rule for that.
- Now refactor based on these changes.
- Please apply the split now.
- Please move docs out of source.