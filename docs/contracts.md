# Data contracts (v1, frozen in Stage A)

These are the records every component reads and writes, from the graph to the agents.

| Where | What |
|---|---|
| [`core/schemas.py`](../src/repobridge/core/schemas.py) | The contracts and their field rules |
| [`core/rules.py`](../src/repobridge/core/rules.py) | Rules that span several records |
| [`docs/schemas/`](schemas/) | Generated JSON Schema files (draft 2020-12) |
| [`testing/fixtures/toy_investigation/records.jsonl`](../testing/fixtures/toy_investigation/records.jsonl) | Worked example that uses every contract |

The design choices behind them are recorded in [ADR-0004](decisions/ADR-0004-contract-implementation.md).

**To change a contract:**
1. Open a `core/*` PR.
2. Bump the version in `SCHEMA` (e.g. `/v1` → `/v2`).
3. Run `repobridge schemas --export docs/schemas`.
4. Regenerate the fixture with `python -m tests.toy_investigation`.
5. Add an ADR.

CI fails if the committed schemas or the fixture fall out of date.

## Conventions

**Record IDs** take the form `<PREFIX>-<token>`, e.g. `EV-3f9a0c12ab45` or a readable `WO-0142`. Use `ids.new_id(prefix)` to make one. Prefixes:

| Prefix | Record |
|---|---|
| `EDGE` | GraphEdge |
| `EV` | Evidence |
| `LE` | LedgerEvent |
| `WO` | ScoutRequest (work order) |
| `FND` | ScoutFinding |
| `CB` | ContextBundle |
| `SUM` | Summary |
| `STR` | StrategyEdge |
| `GH` | GhostHint |
| `LSN` | Lesson |
| `INV` | Investigation |
| `TASK` | Task |

**Snapshots** are a full 40-hex commit SHA. A dirty working tree adds `+dirty:<12 hex of the diff>`.

**Entity IDs** are readable and tied to a revision: `py:pkg.mod.func@<first 12 hex of the SHA>`, plus `+<8 hex>` when the tree is dirty. Use `ids.entity_id(qualified_name, snapshot)` to make one.

**Fingerprints** are the first 16 hex of the SHA-256 of the source after whitespace normalization. Reformatting doesn't change a fingerprint, but any change to the code does.

**Status lattice:** `proposed → checked → observed → reproduced → regression_checked`, or `refuted`.
- Status may only move forward. Skipping steps is allowed, e.g. `proposed → reproduced`.
- Any status can move to `refuted`, and `refuted` is final.
- The only way back to `proposed` is `rules.invalidate`.

**`confidence`** is `low | medium | high` and is used only for ranking, never as proof.

**Encoding.** Every top-level record serializes with a `"schema"` tag, and decoding is strict:
- Unknown fields, missing fields, wrong types and bad enum values all raise `ContractError`.
- Each error names the path to the bad value, e.g. `ProgramEntity.span.start_line: expected int`.

## Contracts

| Contract (`SCHEMA`) | Fields | Field rules |
|---|---|---|
| `ProgramEntity` (`program_entity/v1`) | entity_id, snapshot, kind, qualified_name, path, span, fingerprint | `entity_id` must agree with `qualified_name` and `snapshot`. `path` is repo-relative with `/` separators. `kind`: `module`, `class`, `function`, `method`, `test`, `variable` |
| `GraphEdge` (`graph_edge/v1`) | edge_id, src, dst, relation, resolved, provenance, snapshot, attrs | Unresolved edges must be `CALLS` or `IMPORTS`, with `dst = "unresolved:<name>"` |
| `Evidence` (`evidence/v1`) | evidence_id, task_id, entity_ids, artifact_ref, digest, producer, status, snapshot, depends_on | `digest` is one line of at most 160 characters. No ghost hints in `depends_on`. Change status with `with_status()` |
| `LedgerEvent` (`ledger_event/v1`) | event_id, investigation_id, section, type, producer, ts, refs, payload | `section`: `postmortem`, `strategy`, `plan`, `execution`. `type` is snake_case. `ts` is ISO 8601 and must include a timezone |
| `ScoutRequest` (`scout_request/v1`) | order_id, investigation_id, question {kind, entity, slot, property}, budget {input_tokens, output_tokens}, bundle_ref, anchors, assumptions, permitted_tools, answer_schema | `slot` is `return`, `self`, `param:x`, `field:x` or `global:x`. `property` is snake_case |
| `ScoutFinding` (`scout_finding/v1`) | finding_id, order_id, claim {entity, slot, property, condition}, cites, confidence, status, needs[] | Must cite at least one item. May not cite ghost hints |
| `ContextBundle` (`context_bundle/v1`) | bundle_id, order_id, token_budget, snapshot, items [{ref, fidelity, role, tokens}], excluded, unresolved, missing_requirements | Item tokens must sum to no more than the budget. Item refs are unique, and no ref is both included and excluded |
| `Summary` (`summary/v1`) | summary_id, entity, slot, property, status, fingerprints {entity_id: fp}, conditions, depends_on | `fingerprints` must include the summary's own entity. No ghost hints in `depends_on` |
| `StrategyEdge` (`strategy_edge/v1`) | strategy_id, situation_sig, strategy (tool sequence), stats {n, localized_rate, mean_tokens, mean_steps} | `situation_sig` is `<area>/<anchor_kind>/<symptom_class>` |
| `GhostHint` (`ghost_hint/v1`) | hint_id, source_investigation, situation_sig, strategy_id, ephemeral, outcome | `ephemeral` is always true. `outcome`: `pending`, `confirmed`, `unused`, `contradicted` |
| `Lesson` (`lesson/v1`) | lesson_id, kind, reason, applies_when, refs | `kind`: `refuted_hypothesis`, `rejected_patch` |

## Rules that span several records (`core/rules.py`)

| Rule | Function |
|---|---|
| A finding may only cite items that were in its bundle | `check_finding_grounded(finding, bundle)` |
| A request, its bundle and its budget must agree | `check_request_matches_bundle(request, bundle)` |
| Every assumption must already be an accepted record | `check_assumptions_closed(request, accepted_ids)` |
| Only summaries at `checked` or above are reused | `is_reusable(summary)` |
| Any fingerprint change sends a summary back to `proposed` | `invalidate(summary, current_fingerprints)` |
| Ghost hints are never evidence | Enforced when `Evidence`, `Summary`, `ScoutRequest`, `ScoutFinding` and `ContextBundle` are built |

The check functions return lists of human-readable violations, which the Stage E acceptance gate passes back to scouts. `repobridge validate FILE` runs all of these over a `.json` or `.jsonl` file.
