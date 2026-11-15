# Evaluation plan

## 1. Context-only ladder (runs before any end-to-end repair claim)

Model, temperature (0), tools and total token budget stay the same in every run. Each row adds one thing to the row above.

| Run | Configuration | What it tests |
|---|---|---|
| C0 | Whole files + lexical/BM25 search, single agent | Baseline |
| C1 | + L1 graph expansion from anchors | D1 retrieval |
| C2 | + L3 budgeted bundle with placement policy | D2 attention |
| C3 | + L2 ledger, prompt rebuilt each turn, observation masking | D3 trajectory. Also plots accuracy and tokens against history length (MOSAN never reported this curve) |
| C4 | + two scouts exchanging typed evidence references | D4 cross-agent |
| C4′ | Same as C4, but scouts exchange natural-language summaries | Evidence references vs. summaries |
| C5 | + L4 summaries with invalidation | D5 staleness |
| C6 | + strategy memory and ghost hints | D5 amnesia |
| C7 | Best of C0–C6, with transport switched to NLIP | Transport overhead only |

Configs live in `testing/baselines/`, one YAML per run.

## 2. Measures

- **Context quality:** relevant-entity recall and precision, path recall, and evidence completeness (required items present or listed as missing).
- **Cost:** total and per-agent tokens, mean and maximum prompt size, context-building latency, and amortized index-building cost.
- **Behaviour:** repeated analyses (same entity, slot and property), repeated tool calls, stale-evidence uses, citation-rejection rate, and ghost-hint hit rate.
- **Downstream outcomes, per area:** see §4. Scores from different areas are never combined into one number.

## 3. Data

1. **`testing/fixtures/`**: small synthetic repos with known ground-truth entities and paths, including cross-file chains longer than 4 hops.
2. **Pinned benchmark subsets** in `testing/benchmarks/<area>/manifest.yaml`.

## 4. Per-area evaluation (on `task/*` branches)

| Area | Benchmarks | Baselines (`testing/prior_work/`) | What counts as verified |
|---|---|---|---|
| Debugging / vulnerabilities | SWE-bench Verified / Pro, RepoDebug, selected vulnerability cases | ARISE, RepoAudit, SWE-agent, OpenHands, TraceCoder, PracRepair | Reproduced, then fixed, regression tests pass |
| Optimization | SWE-fficiency (primary), SWE-Perf, FormulaCode | PerfAgent, ACCLAIM | Speed-up beyond noise, correctness tests pass |
| Concurrency | Spaghetti Bench (Kafka bugs), SCTBench, ConVul, RaceBench | ConFixAgent, Fray workflow, REINS | Interleaving reproduced, then gone after the fix |

## 5. End-to-end ablations (midterm report §4.2)

1. Single agent.
2. Multi-agent with free-form messages.
3. Typed NLIP messages, no persistent state.
4. Typed messages with persistent state.
5. Full RepoBridge with scouts and fusion.

Models are local open-weight models through Ollama (Qwen3-Coder, Devstral). Results where the fault location was supplied are reported separately from autonomous localization.
