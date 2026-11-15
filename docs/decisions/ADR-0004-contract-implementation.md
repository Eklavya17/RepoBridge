# ADR-0004: How the v1 data contracts are implemented

**Status:** accepted (2026-11-15, Stage A)

| Choice | Decision | Why |
|---|---|---|
| Library | Frozen standard-library dataclasses, a small strict decoder based on type hints, and hand-written field checks | No dependencies, and the shapes are simple. Revisit pydantic only if the validation code becomes hard to maintain. |
| Entity IDs | Readable `py:pkg.mod.func@<rev12>` | Logs and agent messages stay understandable. The ID is unique within one commit, and the revision tag ties it to the snapshot. |
| Fingerprints | SHA-256 of the source after whitespace normalization, first 16 hex | Reformatting doesn't invalidate summaries, but any change to the code does. |
| Summary dependencies | `fingerprints: {entity_id: fp}` covering the summary's own entity and every source entity it relies on | Invalidation needs the fingerprint of every source the summary depends on, not only its own. This replaces the single `fingerprint` field in the original draft. |
| Confidence | Enum `low/medium/high` | Prevents anyone treating it as a calibrated probability. |
| Versioning | Each contract has a `SCHEMA` tag such as `repobridge.evidence/v1`. JSON Schema files are generated to `docs/schemas/`, and CI checks they are current. | Messages are self-describing, NLIP payloads can be validated later, and any change is visible in the PR. |
| Additions to the draft | `variable` entity kind; `LSN`, `INV` and `TASK` ID prefixes; `pending` hint outcome; `Span`, `Question`, `Budget`, `Claim`, `BundleItem` and `StrategyStats` as typed value objects | The draft needed these to express the toy investigation and the concurrency overlay. |
