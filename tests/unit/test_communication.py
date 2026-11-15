import dataclasses
import json

import pytest
from fastapi.testclient import TestClient

from repobridge.communication.envelope import Envelope, MessageKind, ProtocolError
from repobridge.communication.nlip.codec import from_nlip, nlip_from_wire, nlip_to_wire, to_nlip
from repobridge.communication.nlip.http import BackgroundServer, NLIPHTTPTransport, make_app
from repobridge.communication.transport import InProcessJSONTransport
from repobridge.core import schemas as s
from tests import toy_investigation as toy

RECORDS = toy.build()
REQ = next(r for r in RECORDS if isinstance(r, s.ScoutRequest))
FND = next(r for r in RECORDS if isinstance(r, s.ScoutFinding))
BUNDLE = next(r for r in RECORDS if isinstance(r, s.ContextBundle))
ENTITY = next(r for r in RECORDS if isinstance(r, s.ProgramEntity))
INV = REQ.investigation_id

WORK_ORDER = Envelope(
    kind=MessageKind.WORK_ORDER,
    investigation_id=INV,
    order_id=REQ.order_id,
    records=(REQ,),
    intent="Can transform_config return None?",
)
SAMPLES = [
    WORK_ORDER,
    Envelope(kind=MessageKind.RESULT, investigation_id=INV, order_id=FND.order_id, records=(FND,)),
    Envelope(
        kind=MessageKind.EVIDENCE_REQUEST, investigation_id=INV, refs=("CB-0142", ENTITY.entity_id)
    ),
    Envelope(kind=MessageKind.EVIDENCE_RESPONSE, investigation_id=INV, records=tuple(RECORDS)),
    Envelope(kind=MessageKind.INVALIDATE, investigation_id=INV, refs=("SUM-0001",)),
    Envelope(kind=MessageKind.CANCEL, investigation_id=INV, refs=("WO-0142",)),
    Envelope(kind=MessageKind.ACK, investigation_id=INV),
    Envelope(kind=MessageKind.ERROR, investigation_id=INV, error="boom"),
]


def echo(env: Envelope) -> Envelope:
    return env


def scout(env: Envelope) -> Envelope:
    return env.reply(MessageKind.RESULT, records=(FND,))


@pytest.fixture
def nlip_transport_factory():
    clients = []

    def make(handler):
        client = TestClient(make_app(handler))
        client.__enter__()
        clients.append(client)
        return NLIPHTTPTransport(client=client)

    yield make
    for c in clients:
        c.__exit__(None, None, None)


# ----------------------------------------------------------------------- envelope rules


def test_envelope_kind_constraints():
    with pytest.raises(ProtocolError, match="may not carry"):
        Envelope(
            kind=MessageKind.WORK_ORDER, investigation_id=INV, order_id=REQ.order_id, records=(FND,)
        )
    with pytest.raises(ProtocolError, match="needs an order_id"):
        Envelope(kind=MessageKind.WORK_ORDER, investigation_id=INV, records=(REQ,))
    with pytest.raises(ProtocolError, match="does not match"):
        Envelope(
            kind=MessageKind.WORK_ORDER, investigation_id=INV, order_id="WO-other", records=(REQ,)
        )
    with pytest.raises(ProtocolError, match="needs at least one ref"):
        Envelope(kind=MessageKind.EVIDENCE_REQUEST, investigation_id=INV)
    with pytest.raises(ProtocolError, match="investigation_id"):
        Envelope(kind=MessageKind.ACK, investigation_id="DEBUG-1")
    with pytest.raises(ProtocolError, match="one line"):
        dataclasses.replace(WORK_ORDER, intent="two\nlines")
    with pytest.raises(ProtocolError, match="error text"):
        Envelope(kind=MessageKind.ERROR, investigation_id=INV)


@pytest.mark.parametrize("env", SAMPLES, ids=lambda e: e.kind.value)
def test_plain_json_round_trip(env):
    assert Envelope.from_json(env.to_json()) == env


def test_plain_json_rejects_unknown_fields():
    d = WORK_ORDER.to_dict() | {"extra": 1}
    with pytest.raises(ProtocolError, match="unknown envelope field"):
        Envelope.from_dict(d)


# ----------------------------------------------------------------------- NLIP codec


@pytest.mark.parametrize("env", SAMPLES, ids=lambda e: e.kind.value)
def test_nlip_round_trip_through_wire_json(env):
    wire = nlip_to_wire(to_nlip(env))
    assert from_nlip(nlip_from_wire(json.loads(wire))) == env


def test_nlip_layout_follows_ecma_430():
    msg = to_nlip(WORK_ORDER).to_dict()
    assert msg["messagetype"] == "work_order"
    assert (msg["format"], msg["subformat"], msg["label"]) == ("structured", "json", "envelope")
    subs = {(m["format"], m["subformat"], m.get("label")): m["content"] for m in msg["submessages"]}
    assert subs[("structured", "json", "record")]["schema"] == s.ScoutRequest.SCHEMA
    assert subs[("token", "conversation", None)] == INV
    assert subs[("token", "workorder", "order")] == "WO-0142"
    assert subs[("text", "english", "intent")].startswith("Can transform_config")


def test_entity_refs_are_percent_encoded_uris():
    env = SAMPLES[2]
    uris = [m["content"] for m in to_nlip(env).to_dict()["submessages"] if m.get("label") == "ref"]
    assert uris == ["ev://CB-0142", "ev://py%3Aapp.config.parse_config%40a1b2c3d4e5f6"]


def test_field_names_are_case_insensitive():
    def shout(d):
        return {k.upper() if k != "content" else k: v for k, v in d.items()}

    msg = to_nlip(WORK_ORDER).to_dict()
    loud = shout(msg)
    loud["SUBMESSAGES"] = [shout(m) for m in msg["submessages"]]
    loud["MESSAGETYPE"] = "Work_Order"
    assert from_nlip(nlip_from_wire(loud)) == WORK_ORDER


@pytest.mark.parametrize(
    "mutate,err",
    [
        (lambda m: m.update(messagetype="control"), "control"),
        (lambda m: m.update(messagetype="gossip"), "unknown messagetype"),
        (lambda m: m.update(messagetype="result"), "disagree"),
        (
            lambda m: m["submessages"].append(
                {"format": "generic", "subformat": "x", "content": "?"}
            ),
            "unexpected submessage",
        ),
        (
            lambda m: m.update(
                submessages=[
                    x
                    for x in m["submessages"]
                    if x["format"] != "token" or x["subformat"] != "conversation"
                ]
            ),
            "conversation token",
        ),
        (lambda m: m.update(content={"schema": "something/v9", "kind": "work_order"}), "header"),
    ],
)
def test_nlip_decoder_is_strict(mutate, err):
    msg = to_nlip(WORK_ORDER).to_dict()
    mutate(msg)
    with pytest.raises(ProtocolError, match=err):
        from_nlip(nlip_from_wire(msg))


def test_bad_record_inside_nlip_is_rejected():
    msg = to_nlip(WORK_ORDER).to_dict()
    msg["submessages"][0]["content"]["budget"]["input_tokens"] = -5
    with pytest.raises(ProtocolError, match="bad record"):
        from_nlip(nlip_from_wire(msg))


# ----------------------------------------------------------------------- transports


@pytest.mark.parametrize("env", SAMPLES, ids=lambda e: e.kind.value)
def test_both_transports_deliver_identical_envelopes(env, nlip_transport_factory):
    inproc = InProcessJSONTransport(echo).request(env)
    over_nlip = nlip_transport_factory(echo).request(env)
    assert inproc == over_nlip == env


def test_work_order_gets_finding_over_both(nlip_transport_factory):
    for transport in (InProcessJSONTransport(scout), nlip_transport_factory(scout)):
        reply = transport.request(WORK_ORDER)
        assert reply.kind is MessageKind.RESULT and reply.records == (FND,)
        assert transport.stats.messages == 1 and transport.stats.bytes_out > 0


def test_handler_errors_come_back_as_error_messages(nlip_transport_factory):
    def broken(env):
        raise KeyError("CB-0142")

    for transport in (InProcessJSONTransport(broken), nlip_transport_factory(broken)):
        reply = transport.request(WORK_ORDER)
        assert reply.kind is MessageKind.ERROR and "KeyError" in reply.error
        assert reply.order_id == WORK_ORDER.order_id


def test_mismatched_reply_is_detected(nlip_transport_factory):
    def wrong_order(env):
        return dataclasses.replace(env.reply(MessageKind.ACK), order_id="WO-9999")

    for transport in (InProcessJSONTransport(wrong_order), nlip_transport_factory(wrong_order)):
        with pytest.raises(ProtocolError, match="reply is for order"):
            transport.request(WORK_ORDER)


def test_nlip_server_echoes_conversation_token():
    with TestClient(make_app(echo)) as client:
        resp = client.post(
            "/nlip/",
            content=nlip_to_wire(to_nlip(SAMPLES[6])),
            headers={"content-type": "application/json"},
        )
    tokens = [
        m["content"]
        for m in resp.json()["submessages"]
        if m["format"] == "token" and m["subformat"] == "conversation"
    ]
    assert tokens == [INV]


def test_real_http_server_round_trip():
    with BackgroundServer(make_app(scout)) as srv:
        transport = NLIPHTTPTransport(srv.url)
        try:
            assert transport.request(WORK_ORDER).records == (FND,)
        finally:
            transport.close()
