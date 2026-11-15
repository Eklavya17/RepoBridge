# Performance optimization plug-in (`task/optimization`)

This branch owns only `src/repobridge/tasks/optimization/`, `testing/prior_work/optimization/`, `testing/benchmarks/optimization/` and `configs/experiments/optimization*`. Core changes go to `main` through `core/*` PRs (`docs/branching.md`).

| Plug-in part | Plan |
|---|---|
| Anchors | Profiler hotspots on the benchmark workload |
| Overlay | Cost attributes on nodes (self and cumulative time, allocations) plus hot call paths |
| Question kind | `cost_property`: what in this region grows with input size, and what must an optimization preserve? |
| Summary type | Cost contract: what drives complexity, allocations, side effects |
| Verifier | Repeatable benchmark with a noise threshold, correctness tests, then re-profiling |
| Benchmarks | SWE-fficiency (primary), SWE-Perf, FormulaCode |
| Baselines | PerfAgent, ACCLAIM, general coding agent |

First milestones:
1. Find and pin the PerfAgent and ACCLAIM upstream repos (manifests are TODO).
2. Write a profile → overlay converter (cProfile / py-spy output → cost attributes on entity IDs).
3. Pin a SWE-fficiency subset and record the expert-patch speed-ups.
