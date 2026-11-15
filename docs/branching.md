# Branching and ownership

```
main ───●────────●────────●──────────►   shared core, docs, testing scaffolding
         \        \ merge   \ merge
          \        ▼         ▼
task/debugging ──●───●──────●───────►   tasks/debugging, prior_work/debugging, benchmarks/debugging
task/optimization ─●────●───────────►   same layout for optimization
task/concurrency ───●──────●────────►   same layout for concurrency

core/<topic>, docs/<topic>, testing/<topic>: short-lived, branched from main, merged into main by PR
```

## Rules

1. **`main` is protected by convention.** Changes reach it only through PRs from short-lived `core/*`, `docs/*` or `testing/*` branches. CI must pass.
2. **Task branches are long-lived** and own only:
   - `src/repobridge/tasks/<area>/`
   - `testing/prior_work/<area>/`
   - `testing/benchmarks/<area>/`
   - `testing/fixtures/<area>_*/`
   - `configs/experiments/<area>*`
   - `docs/results/<area>/` (through `docs/*` PRs)
3. **No core edits on a task branch.** If an area needs a core change, open a `core/<topic>` PR to `main`, then merge `main` back into the task branch.
4. **Topic branches** use `<area>/<topic>` (e.g. `debugging/trace-overlay`) and merge into `task/<area>`. Git can't create `task/debugging/<topic>` while `task/debugging` exists.
5. **New dependencies** for one area go in an optional extra named after it (e.g. `optimization = [...]` in `pyproject.toml`), through a small PR to `main`.
6. **Sync:** merge `main` into each task branch weekly, and after every core PR. Merge, don't rebase, since the branches are shared.
7. **Results** from a task branch (tables, plots) go in `docs/results/<area>/` through a `docs/*` PR to `main`. Raw outputs stay in the gitignored `testing/results/`.
8. **Commit messages** start with the area: `core:`, `debugging:`, `optimization:`, `concurrency:`, `testing:`, `docs:`.

## Owners

Who owns what, the reading list and the work packages for each area are in [`team_guide.md`](team_guide.md).
