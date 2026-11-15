# RepoBridge

**Multi-agent reasoning for large-scale repositories.** CS527 Group 14: Eklavya Tyagi, Sunwoo Baek, Vishal Kaushik.

RepoBridge studies whether careful **context management** can help LLM agents with repository-scale QA. The idea is a versioned repository graph, small task-specific context bundles, an investigation ledger, memory tied to repository revisions, and typed agent-to-agent evidence exchange over NLIP. It is evaluated on three areas:

| Area | Branch | Benchmarks |
|---|---|---|
| Debugging and vulnerability detection | `task/debugging` | SWE-bench Verified / Pro, RepoDebug |
| Performance optimization | `task/optimization` | SWE-fficiency, SWE-Perf, FormulaCode |
| Concurrency repair | `task/concurrency` | Spaghetti Bench, SCTBench, ConVul, RaceBench |

> Status: **skeleton**. Modules are stubs that state their responsibility. Implementation follows the build order in [`docs/context_management.md`](docs/context_management.md#6-build-order).

## Start here

1. [`docs/context_management.md`](docs/context_management.md): the five kinds of context dilution and the five-layer design.
2. [`docs/contracts.md`](docs/contracts.md): the data contracts frozen in Stage A.
3. [`docs/evaluation.md`](docs/evaluation.md): context-only ladder C0–C7 and per-area evaluation.
4. [`docs/branching.md`](docs/branching.md): how `main` and the `task/*` branches work.
5. [`docs/communication.md`](docs/communication.md): envelopes, plain JSON and NLIP transports.
6. [`testing/README.md`](testing/README.md): earlier systems, benchmarks and fixtures.

Try it: `uv run python examples/nlip_handoff.py`.

## Setup

```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest
uv run python scripts/fetch_prior_work.py --dry-run
```

Local models are served by Ollama (see `configs/models/`). Copy `.env.example` to `.env` for local settings.

## Layout

```
src/repobridge/   core · ingestion · graph · context · memory · agents · communication · tools · tasks/{debugging,optimization,concurrency} · verification
testing/          prior_work/{context,debugging,optimization,concurrency} · benchmarks · fixtures · baselines · runners · results
tests/            unit · integration · e2e
configs/          models · context · experiments
docs/             design, contracts, evaluation, ADRs, research notes
```
