# Fixtures

Small synthetic repositories with **known ground truth**, used for the context-only ladder
(C0-C6) before real benchmarks. Each fixture folder contains:

- `repo/`: the source tree
- `task.toml`: the issue / anchor (failing test, stack trace, profile frame or race report)
- `ground_truth.toml`: required entities, required call paths, the expected root cause

First fixture to build (Stage B): a cross-file None-propagation bug where the crash site and the
root cause are more than 4 calls apart.
