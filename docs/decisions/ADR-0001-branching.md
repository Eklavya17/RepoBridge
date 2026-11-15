# ADR-0001: Shared core on main, one long-lived branch per area

**Status:** accepted (2026-11-15)

**Context.** Three areas (debugging, optimization, concurrency) are developed in parallel by
different people, but they must share one context engine so that results are comparable and
core reuse can be measured.

**Decision.** `main` holds the core, docs and testing scaffolding, changed only through PRs from
short `core/*`, `docs/*` and `testing/*` branches. `task/debugging`, `task/optimization` and
`task/concurrency` are long-lived and own only their area folders. They merge `main` in
regularly. See `docs/branching.md`.

**Consequences.** Core changes needed by one area are visible to all. Area work never forks the
core. The cost is a weekly merge on each task branch.
