# Examples

Small runnable demonstrations of what is implemented. Each one uses the toy investigation in
`testing/fixtures/toy_investigation/`.

| Script | Shows |
|---|---|
| `nlip_handoff.py` | Coordinator -> scout -> evidence store -> acceptance gate, over in-process JSON and over NLIP/HTTP with real local servers; gate rejects a hallucinated citation; transport overhead |

Run it from the repo root with `uv run python examples/<script>.py`.
