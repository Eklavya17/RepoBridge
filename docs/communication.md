# Communication layer: envelopes, plain JSON and NLIP

Status: **implemented**, as transport only, on branch `core/nlip-transport`. Coordinator and scout logic arrives in Stage E. Code lives in [`src/repobridge/communication/`](../src/repobridge/communication/).

## Design rule

Agents exchange **envelopes** that carry contract records (`core/schemas.py`) by value and everything else by reference. One `Transport` interface has two implementations:

| Transport | Class | Role |
|---|---|---|
| Plain in-process JSON | `InProcessJSONTransport` | The reference transport. All context-management results (C0–C6) are measured on it. |
| NLIP over HTTP | `NLIPHTTPTransport` + `make_app` | Run C7. Uses the official `nlip_sdk` message models and the `nlip_server` FastAPI app. |

Both serialize in each direction, check that each reply matches its request, and count bytes and latency in `TransportStats`. The tests show both deliver **identical envelopes** for every message kind. Any difference in task results between them is therefore a transport bug, not a benefit.

## Envelope (`repobridge.envelope/v1`)

| Field | Meaning |
|---|---|
| `kind` | `work_order`, `result`, `evidence_request`, `evidence_response`, `invalidate`, `cancel`, `ack`, `error` |
| `investigation_id` | `INV-…`. Every message belongs to one investigation |
| `order_id` | `WO-…`. Required for `work_order` and `result`, and must equal the carried record's `order_id` |
| `records` | Contract records. `work_order` carries exactly one `ScoutRequest`, `result` exactly one `ScoutFinding`, `evidence_response` any records. The other kinds carry none |
| `refs` | Record or entity IDs. Required for `evidence_request`, `invalidate` and `cancel` |
| `intent` | Optional single line, 200 characters or fewer, for logs. Never needed for correctness |
| `error` | Required for `error` replies |

Handler exceptions come back as `error` envelopes, never as crashes or bare HTTP failures. A reply for a different investigation or order raises `ProtocolError`.

## Mapping to NLIP (ECMA-430)

| Envelope part | NLIP element |
|---|---|
| `kind` | `messagetype` |
| Header | Main message: `format=structured`, `subformat=json`, `label=envelope`, content `{"schema": "repobridge.envelope/v1", "kind": …, ["error": …]}` |
| Each record | Submessage `structured/json`, `label=record`, content = `record.to_dict()` |
| Each ref | Submessage `structured/uri`, `label=ref`, content `ev://<percent-encoded id>` (e.g. `ev://py%3Aapp.config.parse_config%40a1b2c3d4e5f6`) |
| `investigation_id` | Submessage `token/conversation`. This is NLIP's reserved conversation token, which `nlip_server` echoes back automatically |
| `order_id` | Submessage `token/workorder`, `label=order` (an application token) |
| `intent` | Submessage `text/english`, `label=intent` |

The decoder is strict:
- It rejects control messages, unknown message types, a header that disagrees with `messagetype`, unexpected submessages, a missing conversation token, and invalid records.
- It accepts field names in any letter case, as ECMA-430 requires.

## Running it

```bash
uv pip install -e ".[dev]"
```
```bash
uv run python examples/nlip_handoff.py
```

The example runs coordinator → scout → evidence store → acceptance gate:
1. Over the in-process transport.
2. Over NLIP/HTTP, with two real local servers.
3. It shows the gate rejecting a scout that cites code it was never shown.
4. It shows an error reply.
5. It prints bytes and latency for both transports.

Sample output, Windows laptop with local servers:

```
transport     bytes out   bytes in  median ms
inproc-json         657        543       0.99
nlip-http           973        868      87.54
```

The NLIP latency covers the scout's own two store requests over HTTP. NLIP framing adds about 50% more bytes per message. These are single-run numbers, not benchmarks.

## Notes on the upstream SDK (`nlip_sdk` 0.1.3)

- `NLIP_Message.add_token()` passes `self` twice to `add_submessage`, so it fails. We build token submessages directly instead.
- `extract_conversation_token(label)` ignores its `label` argument. We read tokens ourselves.
- Message content may only be a string or a JSON object, so lists are wrapped: records travel as one submessage each.
- Pinned: `nlip-sdk>=0.1.3,<0.2` and `nlip-server>=0.1.3,<0.2`, both Apache-2.0. Install them with the `nlip` extra; the core package doesn't need them.

## What is not here yet

- **Authentication.** NLIP has an `authorization` token, and ECMA-434 defines security profiles. Everything here runs on localhost only.
- **Out-of-band transfer** of large artifacts (ECMA-430 §6.4). Records are small today, and large traces will move by `ev://` reference.
- **Capability negotiation** over `control` messages.
- **Agent logic.** The scout in the example follows a fixed rule standing in for an LLM. Coordinator, scouts and the gate as components arrive in Stage E.
