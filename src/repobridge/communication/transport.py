"""Transport interface and the plain in-process JSON transport (the reference transport).

A transport delivers a request ``Envelope`` to a handler and returns the handler's reply.
Every transport serializes on the way out and back, so the same bytes-on-the-wire path is
measured whichever transport is used.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from repobridge.communication.envelope import Envelope, check_correlation

Handler = Callable[[Envelope], Envelope]


@dataclass
class TransportStats:
    """Per-transport counters for run C7 (transport overhead)."""

    messages: int = 0
    bytes_out: int = 0
    bytes_in: int = 0
    seconds: list[float] = field(default_factory=list)

    def record(self, bytes_out: int, bytes_in: int, seconds: float) -> None:
        self.messages += 1
        self.bytes_out += bytes_out
        self.bytes_in += bytes_in
        self.seconds.append(seconds)

    def summary(self) -> dict[str, float]:
        n = max(self.messages, 1)
        ordered = sorted(self.seconds) or [0.0]
        return {
            "messages": self.messages,
            "mean_bytes_out": self.bytes_out / n,
            "mean_bytes_in": self.bytes_in / n,
            "median_ms": 1000 * ordered[len(ordered) // 2],
        }


class Transport(Protocol):
    name: str
    stats: TransportStats

    def request(self, envelope: Envelope) -> Envelope:
        """Send ``envelope`` and return the correlated reply (raises ProtocolError)."""
        ...


def safe_handle(handler: Handler, request: Envelope) -> Envelope:
    """Run a handler; turn any exception into an ``error`` reply instead of crashing."""
    try:
        return handler(request)
    except Exception as exc:  # errors travel back as messages, not crashes
        return request.error_reply(f"{type(exc).__name__}: {exc}")


class InProcessJSONTransport:
    """Calls the handler directly, but round-trips both directions through JSON text."""

    name = "inproc-json"

    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.stats = TransportStats()

    def request(self, envelope: Envelope) -> Envelope:
        start = time.perf_counter()
        wire_out = envelope.to_json()
        received = Envelope.from_json(wire_out)
        wire_in = safe_handle(self.handler, received).to_json()
        reply = Envelope.from_json(wire_in)
        self.stats.record(
            len(wire_out.encode()), len(wire_in.encode()), time.perf_counter() - start
        )
        check_correlation(envelope, reply)
        return reply
