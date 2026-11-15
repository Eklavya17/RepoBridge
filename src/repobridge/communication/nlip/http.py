"""NLIP over HTTP: a server built on ``nlip_server`` and a client transport.

    app = make_app(handler)                   # FastAPI app serving POST /nlip/
    transport = NLIPHTTPTransport("http://127.0.0.1:8010")
    reply = transport.request(envelope)

The server runs the handler synchronously per request. Handler errors come back as ``error``
envelopes rather than HTTP failures, so callers handle every outcome the same way.
"""

import time

import httpx
from fastapi import FastAPI
from nlip_sdk.nlip import NLIP_Message
from nlip_server.server import NLIP_Session, SafeApplication, setup_server

from repobridge.communication.envelope import Envelope, ProtocolError, check_correlation
from repobridge.communication.nlip.codec import from_nlip, nlip_from_wire, nlip_to_wire, to_nlip
from repobridge.communication.transport import Handler, TransportStats, safe_handle


class _Session(NLIP_Session):
    def __init__(self, handler: Handler) -> None:
        self.handler = handler

    def execute(self, msg: NLIP_Message) -> NLIP_Message:
        return to_nlip(safe_handle(self.handler, from_nlip(msg)))


class _Application(SafeApplication):
    def __init__(self, handler: Handler) -> None:
        self.handler = handler

    def create_session(self) -> NLIP_Session:
        return _Session(self.handler)


def make_app(handler: Handler) -> FastAPI:
    """FastAPI app exposing ``handler`` at ``POST /nlip/`` (plus nlip_server's health route)."""
    return setup_server(_Application(handler))


class NLIPHTTPTransport:
    """Client side: encode to NLIP, POST, decode the NLIP reply, check correlation."""

    name = "nlip-http"

    def __init__(
        self, base_url: str = "", client: httpx.Client | None = None, timeout: float = 30.0
    ) -> None:
        self.client = client or httpx.Client(base_url=base_url, timeout=timeout)
        self.stats = TransportStats()

    def request(self, envelope: Envelope) -> Envelope:
        start = time.perf_counter()
        body = nlip_to_wire(to_nlip(envelope))
        resp = self.client.post(
            "/nlip/", content=body, headers={"content-type": "application/json"}
        )
        if resp.status_code != 200:
            raise ProtocolError(f"NLIP server returned HTTP {resp.status_code}: {resp.text[:300]}")
        reply = from_nlip(nlip_from_wire(resp.json()))
        self.stats.record(len(body.encode()), len(resp.content), time.perf_counter() - start)
        check_correlation(envelope, reply)
        return reply

    def close(self) -> None:
        self.client.close()


class BackgroundServer:
    """Run an app with uvicorn on a free localhost port in a background thread.

    with BackgroundServer(make_app(handler)) as srv:
        NLIPHTTPTransport(srv.url).request(envelope)
    """

    def __init__(self, app: FastAPI, host: str = "127.0.0.1", startup_timeout: float = 10.0):
        self.app, self.host, self.startup_timeout = app, host, startup_timeout
        self.url = ""

    def __enter__(self) -> "BackgroundServer":
        import threading

        import uvicorn

        self._server = uvicorn.Server(
            uvicorn.Config(self.app, host=self.host, port=0, log_level="warning")
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + self.startup_timeout
        while not self._server.started:
            if time.monotonic() > deadline or not self._thread.is_alive():
                raise RuntimeError("NLIP server did not start")
            time.sleep(0.02)
        port = self._server.servers[0].sockets[0].getsockname()[1]
        self.url = f"http://{self.host}:{port}"
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)
