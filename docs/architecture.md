# RepoBridge architecture

RepoBridge builds context collaboratively, stores it persistently, communicates it in structured form and verifies every proposed fix. This is a working design that changes as results come in (midterm report §2.1). The context-management layer is the main contribution; see `context_management.md`.

```
Inputs                Shared core                         Discovery        Evidence          Solution        Verification
───────               ───────────                         ─────────        ────────          ────────        ────────────
repo @ commit ─► ingestion ─► L1 versioned graph ─┐
issue / test /                (+ task overlays)   ├─► coordinator ─► scouts ─► L5 gate ─► L2 ledger + ─► solution ─► tests / benchmarks /
profile / race ───────────────────────────────────┘   (prompt         (one       (schema,   evidence store  agents      Fray schedules
                                                       rebuilt from    question   cites,     L4 memory                   │
                                                       ledger)         each)      order)                                 │
                                                          ▲                                                              │
                                                          └──────────── results, failed attempts, lessons ◄──────────────┘
```

## Packages (`src/repobridge/`)

| Package | Layer | Responsibility |
|---|---|---|
| `core/` | — | IDs, config, data contracts (`schemas.py`) |
| `ingestion/` | L1 | Parse the repo (Python `ast`), extract symbols, calls, imports, tests |
| `graph/` | L1 | SQLite store, traversal, slicing, task overlays |
| `context/` | L3 | Anchors, expansion, bundle builder, fusion, observation masking |
| `memory/` | L2/L4 | Evidence store, ledger, summaries, strategy memory, ghost hints, lessons |
| `agents/` | L3/L5 | Coordinator, scouts, acceptance gate |
| `communication/` | — | Envelopes, plain JSON transport, NLIP codec + HTTP transport (see `communication.md`) |
| `tools/` | — | Tool functions exposed to agents; MCP server stubs |
| `tasks/<area>/` | plug-in | Anchors, question kinds, overlay, verifier hook for each area |
| `verification/` | — | Test, benchmark and controlled-schedule runners |

Protocols: MCP connects agents to tools, NLIP connects agents to each other, and the evidence store sits behind both.

## Repository layout outside `src/`

- `testing/`: earlier systems (manifests and adapters), benchmark manifests, fixtures, baseline configs, runners, results (gitignored). See `testing/README.md`.
- `tests/`: unit, integration and end-to-end tests for our own code.
- `configs/`: model, context-budget and experiment configs.
- `scripts/`: CLIs (for example `fetch_prior_work.py`).
- `docs/`: design, contracts, evaluation, decisions (ADRs), research notes.
