# Context management: how RepoBridge handles context dilution

Status: **design frozen for Stage A–C** (contracts, graph and bundle builder). Layers L2–L5 stay open to change as C0–C3 results come in. Change this file through a `docs/*` PR, and record any decision change in `docs/decisions/`.

## 1. The problem

Our main claim, from the midterm report and slides: at repository scale, today's models fail mostly because they are given the wrong context, not because they reason badly. Agents read too much, miss dependencies across modules, search the same things again and lose earlier findings. We call the general effect **context dilution**: as more history, tool output and loosely related code pile up, the useful evidence shrinks as a share of the prompt and reasoning gets worse. The term comes from MOSAN (see `references.md`), which describes strategic reasoning degrading as experiment history accumulates.

Evidence that this is real for code:

- **Position effects.** Code-reasoning accuracy drops sharply when the relevant snippet sits in the middle of a long context ("Sense and Sensitivity", arXiv 2505.13353).
- **Long-range dependencies.** Accuracy falls when a function's callee appears far away in the prompt, and adding call-graph hints improves multi-hop retrieval (arXiv 2407.21049).
- **Whole-repo concatenation** hurts, and dependency-preserving pruning helps (Hierarchical Context Pruning, arXiv 2406.18294).
- **Agent trajectories.** Tool observations are most of each turn's tokens. Masking old observations is a strong, cheap baseline, while learned or latent compression can lower resolve rates (SWE-Pruner, Context-as-a-Tool, arXiv 2605.11051).
- **RepoAudit.** Input tokens outweigh output tokens by about 13:1, and turning off its memory raises cost about 3.5×. See `docs/research/Sub-agent Context Architecture.md`.

## 2. Five kinds of dilution

| # | Kind | Symptom in repo agents | Mechanism | Metric |
|---|---|---|---|---|
| D1 | **Retrieval** | Nearby or similar-looking files crowd out the real callers and dependencies | L1 graph + L3 anchored expansion | Relevant-entity recall and precision of a bundle |
| D2 | **Attention** | Key facts get lost in a long prompt or buried in the middle | L3 token budget + placement policy | Tokens per bundle; accuracy against where the key item sits |
| D3 | **Trajectory** | Long chats bury earlier findings and failed hypotheses | L2 ledger, prompt rebuilt each turn, observation masking | Repeated analyses; accuracy and tokens against history length |
| D4 | **Cross-agent** | Free-form summaries drop spans, conditions and provenance | L2 typed findings that carry evidence IDs; L5 gate | Citation-rejection rate; message bytes |
| D5 | **Staleness / amnesia** | Facts from an old commit are reused, or lessons are lost between tasks | L4 revision-scoped memory with invalidation; strategy memory and ghost hints | Stale-evidence rate; hint hit rate |

## 3. Five-layer architecture

```
 issue / failing test / profile / race report
        │
        ▼
 L3  Context assembly ── anchors → graph expansion → narrow → bundle (budget, ordering, excluded/unresolved)
        │      ▲                                               │
        │      │ queries                                       ▼
 L1  Versioned repo graph (+ task overlays)          ephemeral scout (one question)
        ▲                                                      │ typed finding (cites, needs)
        │ invalidation on edit                                 ▼
 L4  Memory: summaries · strategy graph · ghost hints · lessons ◄── L5 Acceptance gate
        ▲                                                      │
        └──────────── L2 Investigation ledger + evidence store ◄┘
                      (coordinator prompt rebuilt from here each turn)
```

### L1: Versioned repository graph
*Prior work: ARISE (multi-granularity graph and slicing), LocAgent (heterogeneous code graph and multi-hop tools), RepoScope (call-chain-aware views).*

- **Language and parser.** Python first, using the standard `ast` module. tree-sitter comes later for other languages.
- **Nodes:** `module`, `class`, `function`, `method`, `test`.
- **Edges:** `CONTAINS`, `IMPORTS`, `CALLS`, `INHERITS`, `DEF_USE` (within one function), `TESTS`.
- **Unresolved calls** (dynamic dispatch, callbacks) are stored as `CALLS` with `resolved=false`. They are never guessed.
- **Every record** carries a `snapshot` (the commit SHA), a `provenance` (`static | observed | llm_inferred`) and a source span.
- **Storage** is SQLite with indexed symbol search. A heavier graph database is added only if measurements call for it.
- **Task overlays** attach to the same entity IDs:
  - Debugging: traces and coverage, as `observed` `CALLS` edges and runtime values.
  - Optimization: profile hotspots, as cost attributes on nodes plus hot call paths.
  - Concurrency: shared variables, locks and thread entry points, as `ACCESSES` and `GUARDED_BY` edges and a static happens-before (SHB) view, as in ConFixAgent.
- **Query tools:** `find_symbol`, `callers`, `callees`, `ego_graph(k)`, `backward_slice`, `call_chains(src, dst)`.

### L2: Investigation ledger and evidence store
*Prior work: MOSAN's Single Ledger Architecture (SiLA) and Decider without chat history; JetBrains-style observation masking; ACE delta updates.*

MOSAN keeps one markdown ledger per cycle, with sections for continuity, post-mortem, strategy, plan and decider log. Its Decider runs **without any chat history**. We keep that idea and make it typed and queryable:

- **One append-only ledger per investigation.** It is made of `LedgerEvent` rows with a `section` in `postmortem | strategy | plan | execution`.
  - `postmortem` holds deterministic numbers from the last cycle only: tests, metrics and bundle statistics. No strategy goes here, as in MOSAN's Lead Analyst.
  - `strategy` holds open hypotheses, the frontier and the lessons that apply.
  - `plan` holds work orders with a step budget.
  - `execution` holds tool calls and results, by reference.
- **The prompt is rebuilt each turn.** The coordinator never accumulates chat history. Each turn its prompt is rendered from the ledger as the top-N frontier items, open hypotheses, budget left and counts for the rest. Its size is therefore bounded no matter how long the investigation runs.
- **Observation masking.** Raw tool output (file text, traces, profiles, logs) goes into the evidence store under an ID. Transcripts and messages carry only `EV-123: <one-line digest>`, and agents dereference IDs only when they need the content.
- **Cycle compression.** At the end of a cycle, a summarizer → critic → consolidator pass (MOSAN) produces **delta entries**: itemized bullets that are appended or edited, never a full rewrite. ACE shows that full rewrites shrink context into generic text ("context collapse").

### L3: Context assembly (find → narrow → spawn)
*Prior work: RepoAudit (demand-driven exploration), RepoScope (structure-preserving serialization), Sub-agent Context Architecture §5.*

1. **Anchor.** Start from the issue text, a stack frame, a failing test, a profiler frame or a race report.
2. **Expand on demand** along graph edges. Depth limit, node budget and unresolved paths are recorded on every expansion.
3. **Narrow.** A sub-agent is spawned only when the question is down to one entity, one slot (a parameter, return value, field or global) and one property. Questions a tool can settle, or that a valid summary already answers, spawn nothing.
4. **Pack a `ContextBundle`** within the token budget:
   - Essential spans at full fidelity; neighbours as signatures or summaries.
   - Call-chain order is preserved.
   - **Placement policy:** the anchor and essential facts go first, the open question last, and supporting items in the middle. This counters the mid-context drop.
   - Required `excluded[]` and `unresolved[]` lists, plus a completeness check that each required caller and test is either present or listed as missing.
   - A slice that is too large is **split** (by branch region or callee), never truncated.

### L4: Memory across investigations
*Prior work: MOSAN's graph memory and ghost nodes, RepoAudit memory (generalized), TraceCoder lessons, ACE.*

- **Knowledge memory.** `Summary` records are keyed by `(entity@rev, slot, property)` and hold a value-flow, cost or synchronization contract.
  - Status lattice: `proposed → checked → observed → reproduced → regression-checked`, or `refuted`.
  - Only summaries at `checked` or above are reused across tasks.
  - Each summary stores a fingerprint of the spans it depends on, and an edit to any of them sends it back to `proposed`.
- **Strategy memory** (adapted from MOSAN's graph memory). In MOSAN, nodes are configuration states and edges are tools, with Q-vectors over the outcomes. In RepoBridge:
  - Nodes are **situation signatures**: task area, anchor kind and symptom class, e.g. `debugging / stack-trace / AttributeError-on-None`.
  - Edges are **strategies**: a tool or sequence of tool calls, e.g. `backward_slice → callers(k=2)`.
  - Edge stats are running means of {localized?, tokens, steps}, updated with α=0.1. Updates are deltas only.
- **Ghost hints** (adapted from MOSAN's ghost nodes):
  - Trigger: an investigation starts with little strategy memory for its signature.
  - The top-k strategies from similar past signatures are injected, marked `ephemeral=true, status=unverified`.
  - They may shape only the coordinator's **plan**. They never enter evidence or count as facts.
  - At the end, a hint that an accepted finding supported is kept as a normal strategy edge. Otherwise it is dropped, and the outcome is logged so the hint hit rate can be reported.
  - MOSAN itself drops ghosts on save and never validates them, so validation is our addition.
- **Lessons.** Refuted hypotheses and rejected patches, with the conditions under which they apply (TraceCoder). They are shown to later agents as short "do not repeat" bullets.

### L5: Acceptance gate
Checks run before any finding enters the store:
1. **Schema:** the payload validates against the answer schema.
2. **Citations:** every citation was in the bundle the agent was given. A claim citing unseen code is rejected.
3. **Order:** ordering along the cited control flow is checked by parsing, as in RepoAudit.
4. **Assumptions:** every assumption is already an accepted fact.

A failed finding is retried once with the failure reason, then logged as an unsupported claim. Confidence scores and ghost hints never count as proof.

## 4. Rules that hold everywhere

1. **Tools retrieve; the LLM reasons.** The LLM is never handed a whole file when a slice exists.
2. **Facts flow; reasoning does not.** Only gated findings reach other agents.
3. **References, not content.** Messages carry evidence IDs, and content is fetched by ID.
4. **Every record is tied to a revision** and has a status.
5. **Transport doesn't matter for the claims.** Every context result must hold over plain in-process JSON. NLIP is measured separately with identical payloads (run C7).

## 5. How each area plugs in

| | Debugging / vulnerabilities | Optimization | Concurrency |
|---|---|---|---|
| Anchors | Failing test, stack trace, issue text | Profiler hotspots on a workload | Race/deadlock report, shared-variable accesses |
| Overlay | Traces, coverage | Cost attributes, hot paths | `ACCESSES`, `GUARDED_BY`, SHB |
| Question kind | `slot_property` | `cost_property` | `access_property` |
| Summary type | Value-flow contract | Cost contract | Synchronization contract |
| Verified means | Reproduced, then fixed, regression-checked | Speed-up beyond noise, tests pass | Interleaving reproduced, then gone after the fix (Fray) |

Each area lives on its `task/<area>` branch and must not change L1–L5. Changes the core needs go to `main` through `core/*` PRs. We count how much of the core each area reuses unchanged, as evidence that the design generalizes.

## 6. Build order

| Stage | Build | Done when |
|---|---|---|
| A | Contracts (`core/schemas.py`) + CLI | Schemas and unit tests pass; a toy task can be represented |
| B | L1 graph | Exact caller/callee queries pass on `testing/fixtures` |
| C | L3 bundle builder + baselines C0–C2 | Recall and token numbers on fixtures |
| D | L2 ledger, prompt rebuild, masking (C3) | A second agent reuses evidence without searching again |
| E | Two scouts + L5 gate (C4) | Typed handoff and retry tests pass |
| F | L4 summaries and invalidation (C5), strategy memory and ghost hints (C6) | Numbers for C5 and C6 |
| G | Area overlays on `task/*` branches | One reproducible investigation per area |

## 7. Open questions

- Whether the static happens-before view for Python threads is precise enough, or whether we need Java (Fray, Spaghetti Bench) for concurrency.
- Embedding-based retrieval: add it only if C1 shows lexical search plus the graph missing concept-level matches (RepoLens).
- The right granularity for spawning sub-agents, given the fixed system-prompt cost of each agent. This is a parameter to tune, not a fixed rule.
- Whether evidence references beat natural-language summaries (C4 against C4′). If not, the evidence-reference claim is dropped.
