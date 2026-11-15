# Runners

One script per (system, benchmark) pair. Each runner must:
1. run in an isolated environment (venv/container) using the pinned upstream commit,
2. write raw outputs to `testing/results/<system>/<run-id>/`,
3. record model, versions, budget and wall-clock time in `run.json`.
