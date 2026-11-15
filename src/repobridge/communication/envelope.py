"""Transport-neutral message envelope for agent-to-agent communication.

An ``Envelope`` carries contract records (``core/schemas.py``) plus routing information.
Every transport, whether plain in-process JSON or NLIP over HTTP, must deliver the same
envelope unchanged. That is what lets context-management results be compared across
transports (docs/context_management.md §4, rule 5).
"""

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from repobridge.core import ids
from repobridge.core import schemas as s
from repobridge.core.serialization import Contract, ContractError

ENVELOPE_SCHEMA = "repobridge.envelope/v1"
MAX_INTENT_CHARS = 200


class ProtocolError(ValueError):
    """A message is malformed or its reply does not match its request."""


class MessageKind(StrEnum):
    WORK_ORDER = "work_order"  # coordinator -> scout: one ScoutRequest
    RESULT = "result"  # scout -> coordinator: one ScoutFinding
    EVIDENCE_REQUEST = "evidence_request"  # any -> store: refs to fetch
    EVIDENCE_RESPONSE = "evidence_response"  # store -> any: the requested records
    INVALIDATE = "invalidate"  # store -> agents: refs that are no longer valid
    CANCEL = "cancel"  # coordinator -> scout: refs of orders to drop
    ACK = "ack"  # receipt for invalidate / cancel
    ERROR = "error"  # any reply that failed; `error` says why


# Which record types each kind may carry, and whether `refs` is required.
_ALLOWED: dict[MessageKind, tuple[tuple[type[Contract], ...], int, int, bool]] = {
    # kind: (record types, min records, max records, refs required)
    MessageKind.WORK_ORDER: ((s.ScoutRequest,), 1, 1, False),
    MessageKind.RESULT: ((s.ScoutFinding,), 1, 1, False),
    MessageKind.EVIDENCE_REQUEST: ((), 0, 0, True),
    MessageKind.EVIDENCE_RESPONSE: (s.CONTRACTS, 0, 10_000, False),
    MessageKind.INVALIDATE: ((), 0, 0, True),
    MessageKind.CANCEL: ((), 0, 0, True),
    MessageKind.ACK: ((), 0, 0, False),
    MessageKind.ERROR: ((), 0, 0, False),
}


@dataclass(frozen=True)
class Envelope:
    kind: MessageKind
    investigation_id: str
    order_id: str | None = None
    records: tuple[Contract, ...] = ()
    refs: tuple[str, ...] = ()
    intent: str | None = None  # at most one sentence, for logs; never needed for correctness
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "refs", tuple(self.refs))
        if not ids.is_record_id(self.investigation_id, "INV"):
            raise ProtocolError(
                f"investigation_id must be 'INV-...', got {self.investigation_id!r}"
            )
        if self.order_id is not None and not ids.is_record_id(self.order_id, "WO"):
            raise ProtocolError(f"order_id must be 'WO-...', got {self.order_id!r}")
        types_, lo, hi, refs_required = _ALLOWED[self.kind]
        if not lo <= len(self.records) <= hi:
            raise ProtocolError(
                f"{self.kind} carries {len(self.records)} records, expected {lo}..{hi}"
            )
        bad = [type(r).__name__ for r in self.records if not isinstance(r, types_)]
        if bad:
            raise ProtocolError(f"{self.kind} may not carry {bad}")
        if refs_required and not self.refs:
            raise ProtocolError(f"{self.kind} needs at least one ref")
        for r in self.refs:
            if not (ids.is_record_id(r) or ids.is_entity_id(r)):
                raise ProtocolError(f"ref {r!r} is neither a record ID nor an entity ID")
        if self.kind in (MessageKind.WORK_ORDER, MessageKind.RESULT):
            if self.order_id is None:
                raise ProtocolError(f"{self.kind} needs an order_id")
            if self.records[0].order_id != self.order_id:
                raise ProtocolError("order_id does not match the carried record")
        if self.kind is MessageKind.ERROR and not self.error:
            raise ProtocolError("error messages need an error text")
        if self.intent is not None and ("\n" in self.intent or len(self.intent) > MAX_INTENT_CHARS):
            raise ProtocolError(f"intent must be one line of at most {MAX_INTENT_CHARS} chars")

    # ------------------------------------------------------------------ plain JSON encoding

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema": ENVELOPE_SCHEMA,
            "kind": self.kind.value,
            "investigation_id": self.investigation_id,
            "records": [r.to_dict() for r in self.records],
            "refs": list(self.refs),
        }
        for key in ("order_id", "intent", "error"):
            if getattr(self, key) is not None:
                out[key] = getattr(self, key)
        return out

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: Any) -> "Envelope":
        if not isinstance(data, dict) or data.get("schema") != ENVELOPE_SCHEMA:
            raise ProtocolError(f"not a {ENVELOPE_SCHEMA} message")
        unknown = set(data) - {
            "schema",
            "kind",
            "investigation_id",
            "order_id",
            "records",
            "refs",
            "intent",
            "error",
        }
        if unknown:
            raise ProtocolError(f"unknown envelope field(s) {sorted(unknown)}")
        try:
            kind = MessageKind(data.get("kind"))
            records = tuple(s.load(r) for r in data.get("records", []))
        except ValueError as exc:  # includes ContractError
            raise ProtocolError(str(exc)) from exc
        return cls(
            kind=kind,
            investigation_id=data.get("investigation_id", ""),
            order_id=data.get("order_id"),
            records=records,
            refs=tuple(data.get("refs", [])),
            intent=data.get("intent"),
            error=data.get("error"),
        )

    @classmethod
    def from_json(cls, text: str) -> "Envelope":
        try:
            return cls.from_dict(json.loads(text))
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"invalid JSON: {exc}") from exc

    # ------------------------------------------------------------------ helpers

    def reply(
        self,
        kind: MessageKind,
        records: tuple[Contract, ...] = (),
        refs: tuple[str, ...] = (),
        intent: str | None = None,
    ) -> "Envelope":
        """Build a reply that keeps this message's correlation (investigation and order)."""
        order = self.order_id
        if kind in (MessageKind.WORK_ORDER, MessageKind.RESULT) and records:
            order = records[0].order_id
        return Envelope(
            kind=kind,
            investigation_id=self.investigation_id,
            order_id=order,
            records=records,
            refs=refs,
            intent=intent,
        )

    def error_reply(self, error: str) -> "Envelope":
        return Envelope(
            kind=MessageKind.ERROR,
            investigation_id=self.investigation_id,
            order_id=self.order_id,
            error=error[:500],
        )


def check_correlation(request: Envelope, reply: Envelope) -> None:
    """A reply must belong to the same investigation and order as its request."""
    if reply.investigation_id != request.investigation_id:
        raise ProtocolError(
            f"reply is for {reply.investigation_id}, request was {request.investigation_id}"
        )
    if request.order_id is not None and reply.order_id != request.order_id:
        raise ProtocolError(f"reply is for order {reply.order_id}, request was {request.order_id}")


__all__ = [
    "ENVELOPE_SCHEMA",
    "ContractError",
    "Envelope",
    "MessageKind",
    "ProtocolError",
    "check_correlation",
]
