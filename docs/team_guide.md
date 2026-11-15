# Team guide: splitting the work across debugging, optimization and concurrency

How to get up to speed on RepoBridge, what each area owner builds, and how three people can work on separate branches that merge cleanly later. Status is as of **2026-11-15**. Update this file when owners or plans change.

---

## 1. RepoBridge in one paragraph

LLM agents fail on large repositories mostly because they get the **wrong context**: too much loosely related code, missing cross-file dependencies, repeated searches and lost findings. We call this *context dilution*. RepoBridge's main contribution is a **shared context-management layer**, made up of:
- a versioned repository graph,
- small, budgeted context packs,
- an investigation ledger,
- memory tied to repository revisions,
- typed evidence that agents exchange over NLIP.

Debugging, optimization and concurrency are the **three areas used to evaluate it**. They all share one core and differ only in plug-ins. The full design is in [`context_management.md`](context_management.md).

> **A note on "RQ" numbers.** The research notes call the areas RQ1 (debugging), RQ2 (optimization) and RQ3 (concurrency). The midterm report's RQ1–RQ4 are cross-cutting questions instead (current agents, RepoBridge vs. baselines, ablations, generalization). This guide uses area names to avoid confusion.

---

## 2. Where things stand

| Piece | What it is | Branch | State |
|---|---|---|---|
| Skeleton, design docs, prior-work manifests | Repo layout, `testing/`, CI | `main` | On GitHub |
| **Stage A: data contracts** | 11 versioned, validated record types and cross-record rules | `core/contracts` | Done, PR pending |
| **Communication layer** | Envelopes, plain JSON transport, NLIP over HTTP | `core/nlip-transport` | Done, PR pending |
| **Stage B: repository graph** | Python AST → graph; callers/callees/chains/tests/slices; `repobridge index`/`query` | `core/graph-ingestion` | Done, PR pending |
| Stage C: context packs + runs C0–C2 | Anchors → expansion → budgeted pack; first numbers | `core/*` (next) | Not started |
| Stages D–F: ledger, scouts + gate, memory | See `context_management.md` §6 | `core/*` | Not started |
| Area plug-ins | Anchors, overlay, verifier per area | `task/<area>` | Scope README only |

Until the three `core/*` PRs are merged into `main`, some links below only work on those branches.

**Midterm timeline,** mapped to this plan:

| Dates | Core (shared) | Each area branch |
|---|---|---|
| Nov 15–22 | Stage C (packs, C0–C2), core requests from areas (§6) | Reproduce one baseline, pin benchmark subset, build overlay + anchors |
| Nov 23–29 | Stages D–E (ledger, scouts, gate) | Fixture + verifier; run baselines and context ladder on own subset |
| Nov 30–Dec 3 | Merge, ablations | Results tables in `docs/results/<area>/` |
| Dec 4–8 | Final report (due Dec 8) | Write own area section |
| Dec 9–10 | NDSS SafeOSE workshop draft | Review |

---

## 3. Day 1: set up and see it working (about 30 minutes)

```bash
git clone https://github.com/Eklavya17/RepoBridge.git && cd RepoBridge
uv venv && uv pip install -e ".[dev]"
uv run pytest -q                                   # all tests should pass
uv run python examples/nlip_handoff.py             # coordinator -> scout -> store -> gate, over JSON and NLIP
uv run repobridge index testing/fixtures/cross_file_none/repo --snapshot aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
uv run repobridge query chains test_checkout_without_discount shop.config.parse
uv run repobridge query slice shop.config.parse
uv run python scripts/fetch_prior_work.py --dry-run
```

You should see a 5-hop call chain from the failing test to the parser, and a slice that exposes the early `return {}`. If any of these fail, ask in the team channel before going further.

---

## 4. Catch-up reading for everyone (about 4 hours, in order)

| # | Read | Why | Time |
|---|---|---|---|
| 1 | Midterm report (`CS527_Midterm_Report.pdf`, shared drive) and [`research/Research Proposal.md`](research/Research%20Proposal.md) | What we promised and the timeline | 20 min |
| 2 | [`../README.md`](../README.md), [`architecture.md`](architecture.md) | Repo layout and packages | 15 min |
| 3 | [`context_management.md`](context_management.md) | **The core idea**: five kinds of dilution, five layers, build order | 40 min |
| 4 | [`research/Sub-agent Context Architecture.md`](research/Sub-agent%20Context%20Architecture.md) | Why RepoAudit's context handling breaks (C1–C7); the find → narrow → spawn loop; how each area plugs in (§7) | 45 min |
| 5 | [`contracts.md`](contracts.md), then [`../src/repobridge/core/schemas.py`](../src/repobridge/core/schemas.py) | The records everyone reads and writes. Don't invent your own | 30 min |
| 6 | [`graph.md`](graph.md), then [`../tests/unit/test_graph.py`](../tests/unit/test_graph.py) | What the graph answers, and how the ground truth is tested | 30 min |
| 7 | [`communication.md`](communication.md), then [`../examples/nlip_handoff.py`](../examples/nlip_handoff.py) | How agents will talk to each other | 20 min |
| 8 | [`evaluation.md`](evaluation.md) | Context ladder C0–C7 and per-area metrics | 15 min |
| 9 | [`branching.md`](branching.md) and §7 below | How we avoid stepping on each other | 10 min |

**Shared papers.** Skim all of them. Read the one marked ★ closely.
- ★ **RepoAudit** (arXiv 2501.18160): our main baseline and the source of most design decisions. Our notes are in [`research/Debugging Architectures/02 RepoAudit.md`](research/Debugging%20Architectures/02%20RepoAudit.md).
- **MOSAN** (doi 10.1088/2632-2153/ae9fb7): where the ledger, strategy memory and ghost hints come from (`context_management.md` L2/L4).
- **LocAgent** (arXiv 2503.09089) and **RepoScope** (arXiv 2507.14791): graph-based retrieval, which is what our L1/L3 build on.
- **Sense and Sensitivity** (arXiv 2505.13353): evidence that "lost in the middle" happens for code too.

All links are in [`references.md`](references.md).

---

## 5. The three areas

Every area plugs into the same core by providing **anchors** (where retrieval starts), an **overlay** (area-specific facts attached to graph entities), a **question kind**, a **summary type** and a **verifier**. Each area must not change the core (`src/repobridge/` outside `tasks/<area>/`). If you need a core change, ask for it as in §6.

### 5.1 Debugging and vulnerability detection: `task/debugging`

**Goal:** show that graph-backed, budgeted context finds root causes that are far from the crash site, with fewer tokens and less repeated exploration than baselines.

| | |
|---|---|
| Owns | `src/repobridge/tasks/debugging/`, `testing/prior_work/debugging/`, `testing/benchmarks/debugging/`, `testing/fixtures/debugging_*/`, `configs/experiments/debugging*` |
| Anchors | Failing test, stack trace, issue text |
| Overlay | Runtime trace / coverage → `observed` `CALLS` edges and values at spans |
| Question kind | `slot_property` (e.g. "can `transform_config.return` be None, and when?") |
| Verified means | Reproduced, then fixed, then regression tests pass |
| Benchmarks | SWE-bench Verified / SWE-Bench Pro (642 tasks, 11 repos), RepoDebug (22 bug types, 8 languages). Start with Python only |
| Baselines | RepoAudit (run A0), ARISE, SWE-agent, OpenHands, TraceCoder, PracRepair |

**Read, in this order:** [`research/Debugging Architecture Review.md`](research/Debugging%20Architecture%20Review.md), then notes 01 ARISE, 02 RepoAudit, 03 PracRepair, 04 TraceCoder and 05 GraphLocator in [`research/Debugging Architectures/`](research/Debugging%20Architectures/). Then the RepoAudit paper §3–4 and App. C. For the vulnerability lane later: 08 ProtocolGuard, 09 VulTriage, 10 VulnGym.

**Work packages:**

| # | Work | Deliverable | Done when |
|---|---|---|---|
| D1 | Reproduce RepoAudit (pinned in `prior_work/debugging/repoaudit`) on a small subset | README with exact commands, model and versions; `results_parser.py` | Same order of results as the paper on the subset, or a written explanation of the gap |
| D2 | Pin a SWE-bench Verified subset: 20–30 Python tasks with failing tests, spread over call-chain depth | `testing/benchmarks/debugging/manifest.toml` with explicit task IDs | Every task reproduces its failing test locally |
| D3 | Stack-trace and failing-test anchors | `tasks/debugging/anchors.py`: pytest output → entity IDs (needs core request R1) | Correct anchors for the fixture and 5 benchmark tasks |
| D4 | Trace overlay | `tasks/debugging/trace_overlay.py`: run a test under `sys.settrace`/coverage → `observed` edges (needs R2) | The fixture's unresolved `PriceEngine().quote` becomes an observed edge |
| D5 | Second fixture | `testing/fixtures/debugging_<name>/` with ground truth, e.g. a None value through a method on a local object | A ground-truth test passes |
| D6 | Verifier | `tasks/debugging/verifier.py`: reproduce → apply patch → rerun test → regression tests, in a clean environment | Works on fixture and 3 benchmark tasks |

### 5.2 Optimization: `task/optimization`

**Goal:** show that profile-anchored, cross-function context finds the real bottleneck and produces measurable speed-ups with tests passing, compared with PerfAgent/ACCLAIM-style workflows.

| | |
|---|---|
| Owns | `src/repobridge/tasks/optimization/`, `testing/prior_work/optimization/`, `testing/benchmarks/optimization/`, `testing/fixtures/optimization_*/`, `configs/experiments/optimization*` |
| Anchors | Profiler hotspots on the benchmark workload |
| Overlay | Cost attributes on entities (self and cumulative time, call counts, allocations) plus hot call paths |
| Question kind | `cost_property` (what grows with input size here; what must an optimization keep?) |
| Verified means | Speed-up beyond measured noise, correctness tests pass, re-profiling confirms |
| Benchmarks | SWE-fficiency (primary: 498 tasks, 9 repos, compares with expert speed-up), SWE-Perf, FormulaCode (957 bottlenecks) |
| Baselines | PerfAgent, ACCLAIM, a general coding agent |

**Read:** the slides "Current Work Learning for RQ2" and "Updated Architecture for RQ2" in the midterm deck, then the PerfAgent paper (arXiv 2607.19653), ACCLAIM (arXiv 2604.04238), and the SWE-fficiency and SWE-Perf papers (links in [`references.md`](references.md)). From SWE-fficiency, focus on *why* agents fail: localization and reasoning across functions. That is our argument.

**Work packages:**

| # | Work | Deliverable | Done when |
|---|---|---|---|
| O1 | Find and pin the PerfAgent and ACCLAIM code. Their manifests are `TODO` | Manifests with a URL and a full commit SHA, plus a README | `fetch_prior_work.py --only perfagent` clones it |
| O2 | Pin a SWE-fficiency subset of 15–25 Python tasks, recording each expert speed-up | `testing/benchmarks/optimization/manifest.toml` | Each workload runs locally, and its baseline time is recorded with variance |
| O3 | Profile overlay | `tasks/optimization/profile_overlay.py`: cProfile/pyinstrument output → cost attributes keyed by entity ID (needs R1, R2) | The top-5 hotspots of a fixture map to the right entities |
| O4 | Fixture | `testing/fixtures/optimization_<name>/`: a quadratic loop 3+ calls below the entry point, with ground truth (hot path, expected fix) | A ground-truth test passes |
| O5 | Benchmark verifier | `tasks/optimization/verifier.py`: N repeats, median and confidence interval, noise threshold, correctness tests, re-profile | Doesn't report a speed-up on a no-op patch, and does on the expert patch |
| O6 | Reproduce PerfAgent on 3–5 tasks | Results in `testing/results/` (not committed) and a summary table | Numbers recorded with the same model and budget as ours |

### 5.3 Concurrency and race conditions: `task/concurrency`

**Goal:** show that explicit context about shared state, locks and interleavings helps find and repair races and deadlocks, using controlled scheduling as the oracle.

| | |
|---|---|
| Owns | `src/repobridge/tasks/concurrency/`, `testing/prior_work/concurrency/`, `testing/benchmarks/concurrency/`, `testing/fixtures/concurrency_*/`, `configs/experiments/concurrency*` |
| Anchors | Race or deadlock report, failing interleaving, accesses to shared variables |
| Overlay | `ACCESSES` / `GUARDED_BY` edges, `variable` entities, thread entry points, a static happens-before (SHB) view |
| Question kind | `access_property` (which locks guard this access; can it run at the same time as that one?) |
| Verified means | Interleaving reproduced under controlled scheduling, gone after the fix, tests pass |
| Benchmarks | Spaghetti Bench (pinned; 11 real Kafka bugs), SCTBench, ConVul, RaceBench |
| Baselines | ConFixAgent, Fray workflow, REINS |

**Read:** the slides "Current Work Learning for RQ3" and "Updated Architecture for RQ3", then the ConFixAgent paper (arXiv 2604.05753) with a focus on SHB context extraction, the Fray README and docs (`prior_work/concurrency/fray`), and the Spaghetti Bench README. Also read [`research/Sub-agent Context Architecture.md`](research/Sub-agent%20Context%20Architecture.md) §7, the concurrency column.

**The decision this area must make first:**
- Spaghetti Bench and Fray are JVM-based, but our graph currently parses Python only.
- Recommendation: run both tracks below in parallel. The fallback, if the Java front end slips, is to evaluate on Python and Java toy fixtures plus whatever Spaghetti Bench bugs the Java front end can handle.

| Track | What it involves |
|---|---|
| **(a) Java front end** | Request R3: tree-sitter-java → the same `ProgramEntity`/`GraphEdge` records. Unlocks the real benchmarks |
| **(b) Python threading fixture** | Design the overlay and question kind against a Python fixture now, so the logic is ready when Java lands. Python has no Fray equivalent, so its verifier would be a stress or randomized-schedule test, reported as weaker evidence |

**Work packages:**

| # | Work | Deliverable | Done when |
|---|---|---|---|
| X1 | Reproduce one Spaghetti Bench Kafka bug under Fray | README with exact JDK/Gradle commands and the failing schedule | The bug reproduces deterministically from a recorded seed or schedule |
| X2 | Find and pin ConFixAgent and REINS. Their manifests are `TODO` | Manifests + README | Clones at a pinned SHA |
| X3 | Overlay schema design | Short design note + core request R4 (variable entities, `ACCESSES`, `GUARDED_BY` extraction) | Agreed in review; no contract version bump needed, since the types already exist |
| X4 | Fixture | `testing/fixtures/concurrency_<name>/`: a check-then-act race on a shared counter across 2 files, with ground truth (accesses, locks, racing pair) | A ground-truth test passes |
| X5 | Verifier | `tasks/concurrency/verifier.py`: Fray runner for Java, stress runner for Python | Reproduces X1 before the fix and not after the expert fix |
| X6 | Pin a benchmark subset | `testing/benchmarks/concurrency/manifest.toml` (Spaghetti Bench IDs + a few SCTBench) | Each item has a reproduction recipe |

---

## 6. Things areas will need from core (request, don't build on your branch)

Open a GitHub issue titled `core request: …`, or message the core owner. Core work lands on `main` through a `core/*` PR, and you then merge `main` into your branch.

| ID | Request | Needed by | Notes |
|---|---|---|---|
| R1 | `Graph.entity_at(path, line)`: map a file and line (stack frame or profile frame) to the innermost entity | Debugging D3, optimization O3 | Small |
| R2 | `GraphStore.add_overlay(snapshot, edges, entity_attrs)`: attach `observed` edges and attributes to an existing snapshot without re-indexing | Debugging D4, optimization O3, concurrency | Medium. Keeps overlays separate from static edges |
| R3 | Java front end (tree-sitter) producing the same records | Concurrency | Large. Decide owner at the next meeting |
| R4 | `variable` entities plus `ACCESSES`/`GUARDED_BY` extraction (Python first, then Java) | Concurrency X3 | Medium |
| R5 | Stage C context packs, so areas can run C0–C2 on their own fixtures | All | Core's next milestone |

---

## 7. Working separately and merging later

### Branch layout

```
main ─────●──────────●──────────●─────────►  core + docs + shared testing scaffolding (PRs only)
           \  core/<topic> PRs ─┘
task/debugging     ───●───●─merge main─●───►  owned by the debugging owner
task/optimization  ───●───●─merge main─●───►  owned by the optimization owner
task/concurrency   ───●───●─merge main─●───►  owned by the concurrency owner
```

### Rules that keep merges painless

1. **Stay inside your folders** (§5 "Owns"). The core, `README.md`, `pyproject.toml`, CI, `docs/` (except `docs/results/<area>/`) and shared fixtures change only through PRs to `main`.
2. **Topic branches can't be named `task/debugging/x`,** because git refuses a branch path below an existing branch name. Use `debugging/<topic>`, `optimization/<topic>` or `concurrency/<topic>`, and merge them into your `task/<area>` branch.
3. **Merge `main` into your task branch** at least weekly, and right after any core PR you depend on. Merge, don't rebase: task branches are shared.
4. **Use the contracts as they are.** If you need a new field, open a `core/*` PR that bumps the schema version (process in [`contracts.md`](contracts.md)). Don't add private fields or side files.
5. **New dependencies** (profilers, tree-sitter, JDK tooling) go in `pyproject.toml` under an optional extra named after your area (e.g. `[project.optional-dependencies] optimization = [...]`), through a small PR to `main`.
6. **Results:** raw outputs go in `testing/results/` (gitignored). Tables and plots go in `docs/results/<area>/` through a `docs/*` PR.
7. **Upstream code** is never copied into the repo. Pin it in a `manifest.toml` with a full commit SHA, and record the license.
8. **Commit message prefixes:** `debugging:`, `optimization:`, `concurrency:`, `core:`, `testing:`, `docs:`.

### Before opening a PR (any branch)

```bash
uv run ruff check . && uv run ruff format --check src tests scripts examples
uv run pytest -q
uv run repobridge schemas --check docs/schemas
git diff --stat main...HEAD     # task branches: only your folders should appear
```

### Merging an area back into `main`

An area merges into `main` (PR `task/<area>` → `main`) when:
- its plug-in tests pass,
- its fixture's ground-truth test passes,
- its diff against `main` touches only its own folders.

Target the **end of Nov 29**, so the final ablations run on one `main`. After that, each area keeps working on its branch and merges again before the Dec 8 report.

### Weekly rhythm

- **Monday:** 20-minute sync. Each owner gives what landed, what's blocked, and any core requests.
- **Thursday:** merge `main` into all task branches. Core owner reviews pending `core/*` PRs.
- **Every PR** to `main` gets one reviewer from a different area. This keeps everyone familiar with the core.

---

## 8. What each area must deliver for the final report

Don't combine scores across areas into one number.

| Area | Required results |
|---|---|
| All | C0–C2 (later C3–C6) on your own fixture(s): relevant-entity recall/precision, tokens per pack, repeated analyses |
| Debugging | Resolve rate on the subset vs. RepoAudit / SWE-agent, localization recall, reproduction rate, unsupported-claim rate; results split by call-chain depth, with separate rows for runs given the fault location and runs that localize on their own |
| Optimization | Measured speed-up vs. the expert patch (with the noise threshold), correctness pass rate, hotspot localization accuracy |
| Concurrency | Races/deadlocks reproduced, repaired and verified under Fray, vs. ConFixAgent; false-positive rate |

---

## 9. Owners

| Branch / area | Owner | Backup reviewer |
|---|---|---|
| `main` / core (Stages A–C, R1–R5) | Eklavya (author of Stages A–B and the communication layer) | — |
| `task/debugging` | _TBD_ | |
| `task/optimization` | _TBD_ | |
| `task/concurrency` | _TBD_ | |

Fill this in at the next meeting, and mirror it in [`branching.md`](branching.md).
