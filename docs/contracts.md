# Data contracts

These are the records every component reads and writes, from the graph to the agents. They are frozen in **Stage A** and implemented in `src/repobridge/core/schemas.py`. Changing a field after Stage A needs a `core/*` PR and an ADR.

Conventions:
- IDs are strings with a type prefix: `ENT-`, `EDGE-`, `EV-`, `LE-`, `WO-`, `FND-`, `CB-`, `SUM-`, `STR-`, `GH-`.
- `snapshot` is the repository commit SHA. An uncommitted working tree gets `<sha>+dirty:<hash>`.
- `status` uses one lattice everywhere: `proposed | checked | observed | reproduced | regression_checked | refuted`.
- `provenance` is one of `static | observed | llm_inferred`.

| Contract | Fields | Written by | Read by |
|---|---|---|---|
| `ProgramEntity` | snapshot, entity_id, kind (`module/class/function/method/test`), qualified_name, path, span (start_line, end_line), fingerprint | ingestion | graph, context |
| `GraphEdge` | edge_id, src, dst, relation (`CONTAINS/IMPORTS/CALLS/INHERITS/DEF_USE/TESTS/ACCESSES/GUARDED_BY`), resolved, provenance, snapshot, attrs | ingestion, overlays | graph, context |
| `Evidence` | evidence_id, task_id, entity_ids, artifact_ref, digest (one line), producer, status, snapshot, depends_on | tools, scouts | everyone, by ID |
| `LedgerEvent` | event_id, investigation_id, section (`postmortem/strategy/plan/execution`), type, refs, producer, payload, ts | coordinator, gate, verifier | coordinator prompt rendering |
| `ScoutRequest` (work order) | order_id, investigation_id, question {kind, entity, slot, property}, anchors, assumptions, budget {input_tokens, output_tokens}, permitted_tools, bundle_ref, answer_schema | coordinator | scout |
| `ScoutFinding` | finding_id, order_id, claim {entity, slot, property, condition}, cites, status, confidence (ranking only), needs[] | scout | gate, then store |
| `ContextBundle` | bundle_id, order_id, token_budget, items (ordered: ref, fidelity, role), excluded, unresolved, missing_requirements, snapshot | context builder | scout |
| `Summary` | summary_id, entity@rev, slot, property, conditions, status, fingerprint, depends_on | gate (promotion) | context builder |
| `StrategyEdge` | strategy_id, situation_sig, strategy (tool sequence), stats {n, localized_rate, mean_tokens, mean_steps} | memory (end of investigation) | coordinator (planning) |
| `GhostHint` | hint_id, source_investigation, situation_sig, strategy_id, ephemeral=true, outcome (`confirmed/unused/contradicted`) | memory (start of investigation) | coordinator (plan only) |
| `Lesson` | lesson_id, kind (`refuted_hypothesis/rejected_patch`), reason, applies_when, refs | gate, verifier | coordinator, solution agents |

Invariants, checked by tests:
1. Every `Evidence`, `Summary` and `GraphEdge` has a `snapshot`.
2. A `ScoutFinding` may only cite IDs that appear in its `ContextBundle`.
3. `GhostHint` records are never referenced by `Evidence.depends_on` or `Summary.depends_on`.
4. Only `Summary` records at `checked` or above are served across investigations.
5. A changed `fingerprint` on any entity in `depends_on` sends a summary back to `proposed`.
