import dataclasses
import json

import pytest

from repobridge import cli
from repobridge.core import ids, rules
from repobridge.core import schemas as s
from repobridge.core.serialization import ContractError
from tests import toy_investigation as toy

RECORDS = toy.build()
BY_TYPE = {type(r): r for r in RECORDS}
ENTITY = BY_TYPE[s.ProgramEntity]
EVIDENCE = BY_TYPE[s.Evidence]
BUNDLE = BY_TYPE[s.ContextBundle]
FINDING = BY_TYPE[s.ScoutFinding]
REQUEST = BY_TYPE[s.ScoutRequest]
SUMMARY = BY_TYPE[s.Summary]


# --------------------------------------------------------------------- round trips


def test_toy_investigation_covers_every_contract():
    assert {type(r) for r in RECORDS} == set(s.CONTRACTS)


@pytest.mark.parametrize("record", RECORDS, ids=lambda r: f"{type(r).__name__}")
def test_round_trip_dict_and_json(record):
    assert type(record).from_dict(record.to_dict()) == record
    assert s.load(json.loads(record.to_json())) == record


def test_committed_fixture_matches_builder():
    assert toy.FIXTURE.read_text(encoding="utf-8") == toy.to_jsonl(RECORDS)


def test_lists_are_normalised_to_tuples():
    ev = dataclasses.replace(EVIDENCE, entity_ids=list(EVIDENCE.entity_ids))
    assert isinstance(ev.entity_ids, tuple) and ev == EVIDENCE


# --------------------------------------------------------------------- strict decoding


def test_schema_tag_is_required_and_checked():
    d = ENTITY.to_dict()
    del d["schema"]
    with pytest.raises(ContractError, match="schema must be"):
        s.ProgramEntity.from_dict(d)
    d["schema"] = "repobridge.program_entity/v2"
    with pytest.raises(ContractError):
        s.ProgramEntity.from_dict(d)
    with pytest.raises(ContractError, match="unknown schema"):
        s.load(d)


def test_unknown_and_missing_fields_rejected():
    d = ENTITY.to_dict() | {"surprise": 1}
    with pytest.raises(ContractError, match="unknown field"):
        s.load(d)
    d = ENTITY.to_dict()
    del d["fingerprint"]
    with pytest.raises(ContractError, match="missing required field 'fingerprint'"):
        s.load(d)


def test_bad_enum_and_wrong_type_report_path():
    d = ENTITY.to_dict() | {"kind": "lambda"}
    with pytest.raises(ContractError, match=r"ProgramEntity\.kind.*not one of"):
        s.load(d)
    d = ENTITY.to_dict()
    d["span"] = {"start_line": "3", "end_line": 4}
    with pytest.raises(ContractError, match=r"span\.start_line: expected int"):
        s.load(d)


# --------------------------------------------------------------------- ids


def test_entity_id_must_match_snapshot_and_name():
    other = ids.make_snapshot("f" * 40)
    with pytest.raises(ContractError, match="does not match snapshot"):
        dataclasses.replace(ENTITY, snapshot=other)
    with pytest.raises(ContractError, match="qualified_name"):
        dataclasses.replace(ENTITY, qualified_name="app.other")


def test_record_id_prefixes_enforced():
    with pytest.raises(ContractError, match="evidence_id"):
        dataclasses.replace(EVIDENCE, evidence_id="FND-1")
    with pytest.raises(ValueError):
        ids.new_id("NOPE")
    assert ids.new_id("EV", seed="x") == ids.new_id("EV", seed="x")


def test_dirty_snapshot_rev_tag():
    snap = ids.make_snapshot("a" * 40, dirty_diff="diff --git ...")
    assert ids.is_snapshot(snap)
    assert ids.entity_id("pkg.f", snap).startswith("py:pkg.f@aaaaaaaaaaaa+")


def test_fingerprint_ignores_whitespace_only():
    a = ids.fingerprint("def f(x):\n    return x + 1\n")
    assert a == ids.fingerprint("def f(x):\n\n        return   x + 1\n")
    assert a != ids.fingerprint("def f(x):\n    return x + 2\n")


# --------------------------------------------------------------------- field rules


def test_digest_is_one_short_line():
    with pytest.raises(ContractError, match="one line"):
        dataclasses.replace(EVIDENCE, digest="line one\nline two")
    with pytest.raises(ContractError, match="one line"):
        dataclasses.replace(EVIDENCE, digest="x" * 161)


def test_unresolved_edges_are_explicit():
    edge = next(r for r in RECORDS if isinstance(r, s.GraphEdge) and not r.resolved)
    with pytest.raises(ContractError, match="must start with"):
        dataclasses.replace(edge, dst="obj.to_json")
    with pytest.raises(ContractError, match="only CALLS and IMPORTS"):
        dataclasses.replace(edge, relation=s.Relation.INHERITS)


def test_bundle_budget_and_uniqueness():
    with pytest.raises(ContractError, match="over the budget"):
        dataclasses.replace(BUNDLE, token_budget=100)
    with pytest.raises(ContractError, match="unique refs"):
        dataclasses.replace(BUNDLE, items=BUNDLE.items + BUNDLE.items[:1])
    with pytest.raises(ContractError, match="both included and excluded"):
        dataclasses.replace(BUNDLE, excluded=(BUNDLE.items[0].ref,))


def test_ghost_hints_are_never_evidence():
    with pytest.raises(ContractError, match="ghost"):
        dataclasses.replace(EVIDENCE, depends_on=("GH-0001",))
    with pytest.raises(ContractError, match="ghost"):
        dataclasses.replace(SUMMARY, depends_on=("GH-0001",))
    with pytest.raises(ContractError, match="ghost"):
        dataclasses.replace(FINDING, cites=("GH-0001",))
    with pytest.raises(ContractError, match="always ephemeral"):
        dataclasses.replace(BY_TYPE[s.GhostHint], ephemeral=False)


def test_finding_must_cite_something():
    with pytest.raises(ContractError, match="cite at least one"):
        dataclasses.replace(FINDING, cites=())


def test_ledger_timestamp_needs_timezone():
    ev = BY_TYPE[s.LedgerEvent]
    with pytest.raises(ContractError, match="timezone"):
        dataclasses.replace(ev, ts="2026-11-15T21:00:00")


def test_slot_format():
    with pytest.raises(ContractError, match="slot must be"):
        dataclasses.replace(FINDING.claim, slot="the return value")


# --------------------------------------------------------------------- status lattice


def test_status_moves_forward_or_to_refuted_only():
    P, C, Ob, R, G, X = (
        s.Status.PROPOSED,
        s.Status.CHECKED,
        s.Status.OBSERVED,
        s.Status.REPRODUCED,
        s.Status.REGRESSION_CHECKED,
        s.Status.REFUTED,
    )
    assert P.can_become(C) and P.can_become(R) and G.can_become(X)
    assert not C.can_become(P) and not R.can_become(Ob) and not X.can_become(G)
    assert EVIDENCE.with_status(s.Status.REGRESSION_CHECKED).status is G
    with pytest.raises(ContractError, match="cannot move"):
        EVIDENCE.with_status(s.Status.PROPOSED)


# --------------------------------------------------------------------- cross-record rules


def test_finding_grounding():
    assert rules.check_finding_grounded(FINDING, BUNDLE) == []
    outside = next(
        r.entity_id
        for r in RECORDS
        if isinstance(r, s.ProgramEntity) and r.entity_id not in BUNDLE.item_refs
    )
    bad = dataclasses.replace(FINDING, cites=(FINDING.cites[0], outside))
    problems = rules.check_finding_grounded(bad, BUNDLE)
    assert problems == [f"cites items not in bundle CB-0142: {[outside]}"]


def test_request_and_assumptions():
    assert rules.check_request_matches_bundle(REQUEST, BUNDLE) == []
    tight = dataclasses.replace(REQUEST, budget=s.Budget(input_tokens=100, output_tokens=10))
    assert "over the request's input budget" in rules.check_request_matches_bundle(tight, BUNDLE)[0]
    assert rules.check_assumptions_closed(REQUEST, {"EV-trace01"}) == []
    assert rules.check_assumptions_closed(REQUEST, set())


def test_summary_reuse_and_invalidation():
    assert rules.is_reusable(SUMMARY)
    assert not rules.is_reusable(dataclasses.replace(SUMMARY, status=s.Status.PROPOSED))
    assert not rules.is_reusable(dataclasses.replace(SUMMARY, status=s.Status.REFUTED))

    same = dict(SUMMARY.fingerprints)
    assert rules.invalidate(SUMMARY, same) is SUMMARY
    changed = {k: "0" * 16 for k in same}
    reset = rules.invalidate(SUMMARY, changed)
    assert reset.status is s.Status.PROPOSED and rules.stale_entities(SUMMARY, changed)
    refuted = dataclasses.replace(SUMMARY, status=s.Status.REFUTED)
    assert rules.invalidate(refuted, changed).status is s.Status.REFUTED


# --------------------------------------------------------------------- CLI


def test_cli_validates_toy_fixture(capsys):
    assert cli.main(["validate", str(toy.FIXTURE)]) == 0
    assert "OK: 21/21" in capsys.readouterr().out


def test_cli_reports_ungrounded_finding(tmp_path, capsys):
    test_entity = next(
        r.entity_id
        for r in RECORDS
        if isinstance(r, s.ProgramEntity) and r.kind is s.EntityKind.TEST
    )
    bad = dataclasses.replace(FINDING, cites=(test_entity,))  # excluded from the bundle
    records = [r if r is not FINDING else bad for r in RECORDS]
    path = tmp_path / "bad.jsonl"
    path.write_text(toy.to_jsonl(records), encoding="utf-8")
    assert cli.main(["validate", str(path)]) == 1
    assert "cites items not in bundle" in capsys.readouterr().err


def test_committed_json_schemas_are_current(capsys):
    assert cli.main(["schemas", "--check", str(toy.ROOT / "docs" / "schemas")]) == 0


def test_later_stage_commands_say_so(capsys):
    assert cli.main(["bundle"]) == 2
    assert "Stage C" in capsys.readouterr().err
