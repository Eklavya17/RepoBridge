# Fixtures

Small synthetic repositories with **known ground truth**, used for the context-only ladder
(C0-C6) before real benchmarks. Each fixture folder contains:

- `repo/`: the source tree
- `ground_truth.toml`: the task (anchor, error), the root cause, and the exact expected graph
  answers (callers, callees, unresolved calls, chains, tests, slices, decoys)

Fixture order: debugging first (`cross_file_none`), then optimization and concurrency fixtures
on their task branches.

## Available fixtures

- `toy_investigation/records.jsonl`: one record of every contract for the empty-config crash
  (Stage A). Regenerate with `python -m tests.toy_investigation`; validate with
  `repobridge validate testing/fixtures/toy_investigation/records.jsonl`.
- `cross_file_none/`: debugging fixture for Stage B. A missing `discount` key makes
  `lookup_rate` return None, which crashes in `apply_rate`; the test-to-parser chain is 5 hops,
  and `legacy_pricing.py` is a text-similar decoy. Checked by `tests/unit/test_graph.py`.
