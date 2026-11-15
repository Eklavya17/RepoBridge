# Debugging and vulnerability detection plug-in (`task/debugging`)

This branch owns only `src/repobridge/tasks/debugging/`, `testing/prior_work/debugging/`, `testing/benchmarks/debugging/` and `configs/experiments/debugging*`. Core changes go to `main` through `core/*` PRs (`docs/branching.md`).

| Plug-in part | Plan |
|---|---|
| Anchors | Failing test, stack trace, issue text, vulnerability sources |
| Overlay | Runtime traces and coverage, stored as `observed` `CALLS` edges and values at spans |
| Question kind | `slot_property`: can this return value or parameter be None, invalid or tainted, and when? |
| Summary type | Value-flow contract: parameter or return value → property under conditions |
| Verifier | Reproduction test, then fix, then regression tests (`verification/`) |
| Benchmarks | SWE-bench Verified / Pro, RepoDebug, selected vulnerability cases |
| Baselines | RepoAudit (A0), ARISE, SWE-agent, OpenHands, TraceCoder, PracRepair |

First milestones:
1. Reproduce one RepoAudit or ARISE run (`testing/prior_work/debugging/`).
2. Build the cross-file None-propagation fixture and run the context ladder C0–C2 on it.
3. Pin a SWE-bench Verified subset in `testing/benchmarks/debugging/manifest.toml`.
