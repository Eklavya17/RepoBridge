"""End-to-end handoff over the communication layer, using the toy investigation.

    coordinator --work_order--> scout --evidence_request--> evidence store
                                scout <--evidence_response--
    coordinator <--result------ scout
    coordinator runs the acceptance-gate rules on the finding

The same flow runs twice: over the plain in-process JSON transport, and over NLIP/HTTP with
two real local servers (store and scout). The script then checks that both runs produce
identical records and compares message size and latency (run C7).

The scout's "reasoning" is a fixed rule standing in for an LLM (agents arrive in Stage E).
This example demonstrates the communication layer only.

    uv run python examples/nlip_handoff.py
"""

import dataclasses
import json
from pathlib import Path

from repobridge.communication.envelope import Envelope, MessageKind
from repobridge.communication.nlip.http import BackgroundServer, NLIPHTTPTransport, make_app
from repobridge.communication.transport import InProcessJSONTransport, Transport
from repobridge.core import ids, rules
from repobridge.core import schemas as s

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "testing" / "fixtures" / "toy_investigation" / "records.jsonl"


def load_records() -> list[s.Contract]:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    return [s.load(json.loads(line)) for line in lines if line.strip()]


# ------------------------------------------------------------------------ evidence store


def make_store(records: list[s.Contract]):
    by_id = {getattr(r, dataclasses.fields(r)[0].name): r for r in records}

    def store(env: Envelope) -> Envelope:
        if env.kind is MessageKind.EVIDENCE_REQUEST:
            missing = [r for r in env.refs if r not in by_id]
            if missing:
                return env.error_reply(f"unknown refs {missing}")
            return env.reply(
                MessageKind.EVIDENCE_RESPONSE, records=tuple(by_id[r] for r in env.refs)
            )
        if env.kind in (MessageKind.INVALIDATE, MessageKind.CANCEL):
            return env.reply(MessageKind.ACK)
        return env.error_reply(f"store does not handle {env.kind}")

    return store


# ------------------------------------------------------------------------ scout


def make_scout(store_link: Transport, cite_unseen: bool = False):
    """A scout that fetches its bundle by reference and answers with a typed finding."""

    def scout(env: Envelope) -> Envelope:
        req = env.records[0]
        assert isinstance(req, s.ScoutRequest)
        fetch = Envelope(
            kind=MessageKind.EVIDENCE_REQUEST,
            investigation_id=env.investigation_id,
            order_id=req.order_id,
            refs=(req.bundle_ref,),
        )
        bundle = store_link.request(fetch).records[0]
        assert isinstance(bundle, s.ContextBundle)
        ev_refs = tuple(i.ref for i in bundle.items if ids.id_prefix(i.ref) == "EV")
        evidence = store_link.request(dataclasses.replace(fetch, refs=ev_refs)).records

        # Stand-in for LLM reasoning: an early-exit slice means the slot may be None.
        slices = [e for e in evidence if "early exit" in e.digest]
        q = req.question
        cites = (q.entity, *(e.evidence_id for e in slices))
        if cite_unseen:  # simulate a hallucinated citation
            cites += (bundle.excluded[0],)
        finding = s.ScoutFinding(
            finding_id=ids.new_id("FND", seed=req.order_id),
            order_id=req.order_id,
            claim=s.Claim(
                entity=q.entity,
                slot=q.slot,
                property=q.property,
                condition={"var": "cfg", "op": "==", "value": {}},
            ),
            cites=cites,
            confidence=s.Confidence.MEDIUM if slices else s.Confidence.LOW,
        )
        return env.reply(
            MessageKind.RESULT,
            records=(finding,),
            intent=f"{q.property} on {q.slot}: cited {len(cites)} items",
        )

    return scout


# ------------------------------------------------------------------------ coordinator + gate


def investigate(
    scout_link: Transport, store_link: Transport, req: s.ScoutRequest, accepted: set[str]
) -> tuple[s.ScoutFinding, list[str]]:
    order = Envelope(
        kind=MessageKind.WORK_ORDER,
        investigation_id=req.investigation_id,
        order_id=req.order_id,
        records=(req,),
        intent="Can transform_config return None for an empty config?",
    )
    reply = scout_link.request(order)
    if reply.kind is MessageKind.ERROR:
        raise RuntimeError(reply.error)
    finding = reply.records[0]
    bundle = store_link.request(
        Envelope(
            kind=MessageKind.EVIDENCE_REQUEST,
            investigation_id=req.investigation_id,
            order_id=req.order_id,
            refs=(req.bundle_ref,),
        )
    ).records[0]
    problems = (
        rules.check_request_matches_bundle(req, bundle)
        + rules.check_assumptions_closed(req, accepted)
        + rules.check_finding_grounded(finding, bundle)
    )
    return finding, problems


def main() -> None:
    records = load_records()
    req = next(r for r in records if isinstance(r, s.ScoutRequest))
    accepted = {
        r.evidence_id
        for r in records
        if isinstance(r, s.Evidence) and r.status.at_least(s.Status.CHECKED)
    }
    store = make_store(records)

    print("== 1. In-process JSON transport")
    store_in = InProcessJSONTransport(store)
    scout_in = InProcessJSONTransport(make_scout(store_in))
    f_in, problems = investigate(scout_in, store_in, req, accepted)
    print(f"finding {f_in.finding_id}: {f_in.claim.property} when {f_in.claim.condition}")
    print(f"cites {list(f_in.cites)}")
    print(f"gate: {'ACCEPT' if not problems else problems}")

    print("\n== 2. NLIP over HTTP (two local servers)")
    with BackgroundServer(make_app(store)) as store_srv:
        store_http = NLIPHTTPTransport(store_srv.url)
        with BackgroundServer(make_app(make_scout(store_http))) as scout_srv:
            scout_http = NLIPHTTPTransport(scout_srv.url)
            print(f"store at {store_srv.url}/nlip/, scout at {scout_srv.url}/nlip/")
            f_http, problems = investigate(scout_http, store_http, req, accepted)
            print(f"gate: {'ACCEPT' if not problems else problems}")
            print(f"identical finding to in-process run: {f_http == f_in}")

            print("\n== 3. Hallucinated citation is rejected by the gate")
            with BackgroundServer(make_app(make_scout(store_http, cite_unseen=True))) as bad:
                _, problems = investigate(NLIPHTTPTransport(bad.url), store_http, req, accepted)
                print(f"gate: REJECT {problems}")

            print("\n== 4. Errors travel back as messages, not crashes")
            err = store_http.request(
                Envelope(
                    kind=MessageKind.EVIDENCE_REQUEST,
                    investigation_id=req.investigation_id,
                    refs=("EV-doesnotexist",),
                )
            )
            print(f"{err.kind}: {err.error}")

    print("\n== 5. Transport overhead (one work order; the scout makes two store calls inside it)")
    print(f"{'transport':<12} {'bytes out':>10} {'bytes in':>10} {'median ms':>10}")
    for t in (scout_in, scout_http):
        m = t.stats.summary()
        print(
            f"{t.name:<12} {m['mean_bytes_out']:>10.0f} {m['mean_bytes_in']:>10.0f} "
            f"{m['median_ms']:>10.2f}"
        )


if __name__ == "__main__":
    main()
