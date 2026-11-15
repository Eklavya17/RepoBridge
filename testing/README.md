# testing/: earlier systems, benchmarks and experiment harness

This folder is for **reproducing earlier work and running experiments**. Unit tests for our own code live in `/tests`.

| Folder | Holds | Committed? |
|---|---|---|
| `prior_work/<area>/<system>/` | `manifest.yaml` (repo URL and pinned commit), `README.md` (what to reproduce), `adapter/` (their output → our metrics), `results_parser.py` | yes |
| `prior_work/_upstream/` | Upstream clones made by `scripts/fetch_prior_work.py` | **no** (gitignored) |
| `benchmarks/<area>/manifest.yaml` | Dataset, version and the pinned task subset we evaluate | yes |
| `fixtures/` | Small synthetic repos with ground-truth entities and paths | yes |
| `baselines/` | Configs for context-ladder runs C0–C7 | yes |
| `runners/` | Scripts that run one system on one benchmark subset in isolation | yes |
| `results/` | Raw run outputs | **no** (gitignored) |

Areas: `context` (context-management systems, shared by all three), `debugging`, `optimization`, `concurrency`.

## Adding an earlier system

1. Create `prior_work/<area>/<system>/` by copying another system's folder.
2. Fill in `manifest.yaml`. Use only a URL you have checked, and pin `commit` to a full SHA. Leave `TODO` if unknown; the fetch script skips `TODO` entries.
3. Write the reproduction steps and the subset you ran in its `README.md`.
4. Run `python scripts/fetch_prior_work.py --only <system>`.

Upstream code is never copied into this repository, because of licensing. Record each project's license in its manifest.
