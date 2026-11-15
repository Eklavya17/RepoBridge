"""A toy debugging investigation built from every contract (Stage A "done when").

Scenario (docs/research/Sub-agent Context Architecture.md §5): an empty config file crashes
``serializer.write`` because ``transform_config`` returns None for ``{}``.

``python -m tests.toy_investigation`` rewrites testing/fixtures/toy_investigation/records.jsonl.
"""

from pathlib import Path

from repobridge.core import ids
from repobridge.core import schemas as s

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "testing" / "fixtures" / "toy_investigation" / "records.jsonl"

SNAP = ids.make_snapshot("a1b2c3d4e5f6" + "0" * 28)
INV = "INV-toy001"
TASK = "TASK-toy001"
TS = "2026-11-15T21:00:00+00:00"

SOURCES = {
    "app.config.parse_config": "def parse_config(text):\n    return json.loads(text or '{}')\n",
    "app.config.transform_config": "def transform_config(cfg):\n    if not cfg:\n        return None\n"
    "    return {**DEFAULTS, **cfg}\n",
    "app.serializer.write": "def write(obj, out):\n    out.write(obj.to_json())\n",
    "tests.test_serializer.test_empty_config": "def test_empty_config():\n    run('')\n",
}


def eid(qname: str) -> str:
    return ids.entity_id(qname, SNAP)


def build() -> list[s.Contract]:
    parse, transform, write, test = (eid(q) for q in SOURCES)
    fps = {eid(q): ids.fingerprint(src) for q, src in SOURCES.items()}
    spans = {parse: (3, 4), transform: (7, 10), write: (2, 3), test: (5, 6)}
    kinds = {
        parse: s.EntityKind.FUNCTION,
        transform: s.EntityKind.FUNCTION,
        write: s.EntityKind.FUNCTION,
        test: s.EntityKind.TEST,
    }
    paths = {
        parse: "app/config.py",
        transform: "app/config.py",
        write: "app/serializer.py",
        test: "tests/test_serializer.py",
    }

    entities = [
        s.ProgramEntity(
            entity_id=e,
            snapshot=SNAP,
            kind=kinds[e],
            qualified_name=ids.parse_entity_id(e)[1],
            path=paths[e],
            span=s.Span(*spans[e]),
            fingerprint=fps[e],
        )
        for e in (parse, transform, write, test)
    ]
    edges = [
        s.GraphEdge(
            edge_id="EDGE-0001",
            src=test,
            dst=write,
            relation=s.Relation.TESTS,
            resolved=True,
            provenance=s.Provenance.STATIC,
            snapshot=SNAP,
        ),
        s.GraphEdge(
            edge_id="EDGE-0002",
            src=write,
            dst=transform,
            relation=s.Relation.CALLS,
            resolved=True,
            provenance=s.Provenance.OBSERVED,
            snapshot=SNAP,
        ),
        s.GraphEdge(
            edge_id="EDGE-0003",
            src=transform,
            dst=parse,
            relation=s.Relation.CALLS,
            resolved=True,
            provenance=s.Provenance.STATIC,
            snapshot=SNAP,
        ),
        s.GraphEdge(
            edge_id="EDGE-0004",
            src=write,
            dst="unresolved:obj.to_json",
            relation=s.Relation.CALLS,
            resolved=False,
            provenance=s.Provenance.STATIC,
            snapshot=SNAP,
        ),
    ]
    evidence = [
        s.Evidence(
            evidence_id="EV-trace01",
            task_id=TASK,
            entity_ids=(write,),
            artifact_ref="ev://toy/trace/EV-trace01",
            digest="AttributeError: 'NoneType' object has no attribute 'to_json' at "
            "serializer.py:3",
            producer="tool:pytest",
            status=s.Status.REPRODUCED,
            snapshot=SNAP,
        ),
        s.Evidence(
            evidence_id="EV-slice01",
            task_id=TASK,
            entity_ids=(transform,),
            artifact_ref="ev://toy/slice/EV-slice01",
            digest="backward slice of transform_config.return: early exit when not cfg",
            producer="tool:slicer",
            status=s.Status.CHECKED,
            snapshot=SNAP,
        ),
    ]
    request = s.ScoutRequest(
        order_id="WO-0142",
        investigation_id=INV,
        question=s.Question(
            kind=s.QuestionKind.SLOT_PROPERTY,
            entity=transform,
            slot="return",
            property="may_be_none",
        ),
        budget=s.Budget(input_tokens=6000, output_tokens=600),
        bundle_ref="CB-0142",
        anchors=(write,),
        assumptions=("EV-trace01",),
        permitted_tools=("graph.callers",),
    )
    bundle = s.ContextBundle(
        bundle_id="CB-0142",
        order_id="WO-0142",
        token_budget=3000,
        snapshot=SNAP,
        items=(
            s.BundleItem(
                ref="EV-trace01", fidelity=s.Fidelity.SUMMARY, role=s.ItemRole.ANCHOR, tokens=60
            ),
            s.BundleItem(
                ref=transform, fidelity=s.Fidelity.FULL, role=s.ItemRole.ESSENTIAL, tokens=180
            ),
            s.BundleItem(
                ref="EV-slice01", fidelity=s.Fidelity.FULL, role=s.ItemRole.ESSENTIAL, tokens=240
            ),
            s.BundleItem(
                ref=parse, fidelity=s.Fidelity.SIGNATURE, role=s.ItemRole.SUPPORTING, tokens=30
            ),
        ),
        excluded=(test,),
        unresolved=("unresolved:obj.to_json",),
    )
    finding = s.ScoutFinding(
        finding_id="FND-0142",
        order_id="WO-0142",
        claim=s.Claim(
            entity=transform,
            slot="return",
            property="may_be_none",
            condition={"var": "cfg", "op": "==", "value": {}},
        ),
        cites=(transform, "EV-slice01"),
        confidence=s.Confidence.MEDIUM,
        needs=(
            s.Question(
                kind=s.QuestionKind.SLOT_PROPERTY,
                entity=parse,
                slot="return",
                property="may_be_empty_dict",
            ),
        ),
    )
    ledger = [
        s.LedgerEvent(
            event_id="LE-0001",
            investigation_id=INV,
            section=s.LedgerSection.EXECUTION,
            type="reproduced",
            producer="tool:pytest",
            ts=TS,
            refs=("EV-trace01",),
        ),
        s.LedgerEvent(
            event_id="LE-0002",
            investigation_id=INV,
            section=s.LedgerSection.PLAN,
            type="work_order_issued",
            producer="coordinator",
            ts=TS,
            refs=("WO-0142", "CB-0142"),
            payload={"step": 1, "step_budget": 15},
        ),
        s.LedgerEvent(
            event_id="LE-0003",
            investigation_id=INV,
            section=s.LedgerSection.STRATEGY,
            type="finding_accepted",
            producer="gate",
            ts=TS,
            refs=("FND-0142",),
        ),
        s.LedgerEvent(
            event_id="LE-0004",
            investigation_id=INV,
            section=s.LedgerSection.POSTMORTEM,
            type="cycle_metrics",
            producer="analyst",
            ts=TS,
            payload={"bundle_tokens": 510, "repeated_analyses": 0},
        ),
    ]
    summary = s.Summary(
        summary_id="SUM-0001",
        entity=transform,
        slot="return",
        property="may_be_none",
        status=s.Status.CHECKED,
        fingerprints={transform: fps[transform]},
        conditions={"var": "cfg", "op": "==", "value": {}},
        depends_on=("EV-slice01",),
    )
    strategy = s.StrategyEdge(
        strategy_id="STR-0001",
        situation_sig="debugging/stack_trace/attribute_error_on_none",
        strategy=("backward_slice", "callers"),
        stats=s.StrategyStats(n=4, localized_rate=0.75, mean_tokens=5200.0, mean_steps=3.5),
    )
    hint = s.GhostHint(
        hint_id="GH-0001",
        source_investigation="INV-old042",
        situation_sig=strategy.situation_sig,
        strategy_id="STR-0001",
    )
    lesson = s.Lesson(
        lesson_id="LSN-0001",
        kind=s.LessonKind.REJECTED_PATCH,
        reason="None check in serializer.write hides the upstream root cause",
        applies_when="crash site is downstream of a reproduced None source",
        refs=("FND-0142",),
    )
    return [
        *entities,
        *edges,
        *evidence,
        request,
        bundle,
        finding,
        *ledger,
        summary,
        strategy,
        hint,
        lesson,
    ]


def to_jsonl(records: list[s.Contract]) -> str:
    return "".join(r.to_json() + "\n" for r in records)


if __name__ == "__main__":
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(to_jsonl(build()), encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE}")
