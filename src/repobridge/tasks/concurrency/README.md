# Concurrency repair plug-in (`task/concurrency`)

This branch owns only `src/repobridge/tasks/concurrency/`, `testing/prior_work/concurrency/`, `testing/benchmarks/concurrency/` and `configs/experiments/concurrency*`. Core changes go to `main` through `core/*` PRs (`docs/branching.md`).

| Plug-in part | Plan |
|---|---|
| Anchors | Race or deadlock report, failing interleaving, shared-variable accesses |
| Overlay | `ACCESSES` and `GUARDED_BY` edges, thread entry points, a static happens-before view (ConFixAgent-style SHB) |
| Question kind | `access_property`: which locks guard this access, and can it run at the same time as that one? |
| Summary type | Synchronization contract: locks held or released, shared state touched, thread entry |
| Verifier | Fray controlled scheduling: interleaving reproduced, then gone after the fix, with tests passing |
| Benchmarks | Spaghetti Bench (Kafka bugs, pinned), SCTBench, ConVul, RaceBench |
| Baselines | ConFixAgent, Fray workflow, REINS |

Open decision: Spaghetti Bench and Fray target the JVM, so the L1 graph needs a Java front end (tree-sitter) for this area. Raise this as a `core/*` PR.

First milestones:
1. Fetch Fray and Spaghetti Bench and reproduce one Kafka bug under Fray.
2. Find and pin the ConFixAgent upstream repo.
3. Design the `ACCESSES` / `GUARDED_BY` overlay schema (core PR).
