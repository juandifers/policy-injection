"""Phase 2c arms of t01 (pre-registered 2026-11-18): L7 mirror-marker, L5 defended, L6 undeclared (L1-S reuses L1's files with
the schema-only input mode and has no files of its own). Build output of `build_arms.py` under `arms/`, recorded in
`arms/arms-2c.json`; every Phase 2b arm file and `arms/arms.json` keep their committed bytes. Oracle: Dogwood interpreter via
pgi.oracle.temporal, AWS-shaped event schema. Behaviour over traces, except where the pre-registration is about text.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

from pgi.analysis.dogwood_text import close_binding_report
from pgi.generators.dogwood_inputs import load_dogwood_inputs, load_requirements
from pgi.oracle import temporal
from pgi.schemagen import generate_dogwood, link_session_id

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domains" / "assetopsbench"
T01 = DOMAIN / "scenarios" / "t01_close_after_approval"
ARMS = T01 / "arms"
EVENTS = DOMAIN / "schema" / "agentcore.dwschema"
HELD_OUT = {"t15_vendor_enum_only": False, "t16_authority_rejected_vendor_positive": False, "t17_authority_granted_vendor_negative": True}
MARKER_OUTCOMES, MARKER_KINDS = ["SIGNED_OFF", "DECLINED", "QUEUED"], ["OPERATOR", "BOT", "SCHEDULER"]
ARMS_2B_JSON_SHA = "77376b13ad2df77f67a9b42a3e59c06b919b6c41cbd07775244065ee4f777884"   # committed in 30ec689 (Phase 2b prereg)
RUNS_2B = {"v2": "20261118T181007Z-temporal-clean-t01-goal-level-v2", "typed": "20261118T181707Z-temporal-clean-t01-goal-level-typed",
           "L1": "20261118T182621Z-temporal-clean-t01-goal-level-L1", "L2": "20261118T183750Z-temporal-clean-t01-goal-level-L2",
           "L3": "20261118T185148Z-temporal-clean-t01-goal-level-L3", "L4": "20261118T185932Z-temporal-clean-t01-goal-level-L4"}

sys.path.insert(0, str(T01))
import build_arms  # noqa: E402


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _json(p: Path) -> dict:
    return json.loads(p.read_text())


def _dump(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


@pytest.fixture(scope="module")
def rec():
    return _json(ARMS / "arms-2c.json")


@pytest.fixture(scope="module")
def rec2b():
    return _json(ARMS / "arms.json")


@pytest.fixture(scope="module")
def suites():
    return {arm: temporal.load_suite(ARMS / arm / "traces.yaml") for arm in ("typed", "L1", "L2", "L3", "L7", "L5", "L6")}


# ---- additivity
def test_phase_2b_arms_and_their_record_are_byte_identical(rec2b):
    assert sha(ARMS / "arms.json") == ARMS_2B_JSON_SHA
    for arm, entry in rec2b["arms"].items():
        for rel, h in entry["sha256"].items():
            assert sha(ARMS / arm / rel) == h, (arm, rel)
    assert set(rec2b["arms"]) == {"v2", "typed", "L1", "L2", "L3", "L4"}


def test_2c_record_names_three_arms_and_hashes_match(rec):
    assert set(rec["arms"]) == {"L7", "L5", "L6"}
    for arm, entry in rec["arms"].items():
        for rel, h in entry["sha256"].items():
            assert sha(ARMS / arm / rel) == h, (arm, rel)
    assert rec["L1-S"]["arm_files"] == "L1" and rec["L1-S"]["input_mode"] == "schema-only"
    assert rec["built_from"]["arms_json_sha256"] == ARMS_2B_JSON_SHA


def test_scenario_yaml_selects_the_2c_arms():
    l7 = load_dogwood_inputs(T01, intent="goal-level", arm="L7")
    l5 = load_dogwood_inputs(T01, intent="goal-level", arm="L5")
    l6 = load_dogwood_inputs(T01, intent="goal-level", arm="L6")
    v2 = load_dogwood_inputs(T01, intent="goal-level", arm="v2")
    typed = load_dogwood_inputs(T01, intent="goal-level", arm="typed")
    for a in (l7, l6):
        assert a.manifest_paths[1] == v2.manifest_paths[1] and a.hashes["manifest:authority"] == v2.hashes["manifest:authority"]
        assert a.gold == v2.gold and a.hashes["gold"] == v2.hashes["gold"]
    assert l7.manifest_paths[0] == ARMS / "L7" / "manifests" / "wo.tools.json" and l6.manifest_paths[0] == ARMS / "L6" / "manifests" / "wo.tools.json"
    assert l5.manifest_paths[1] == typed.manifest_paths[1] and l5.hashes["manifest:authority"] == typed.hashes["manifest:authority"]
    assert l5.manifest_paths[0] == ARMS / "L2" / "manifests" / "wo.tools.json"           # L2's vendor entry, the same file
    assert l5.gold == ARMS / "L5" / "gold.dw" and l5.hashes["gold"] == typed.hashes["gold"]  # typed gold, same bytes
    for a in (l7, l5, l6):
        assert a.schema_path == ARMS / a.arm_name / "schema" / "t01.dogwood.cedarschema"
        assert a.traces_yaml == ARMS / a.arm_name / "traces.yaml" and a.requirements == ARMS / a.arm_name / "requirements.yaml"
        assert a.hashes["intent"] == v2.hashes["intent"] and a.catalogue == T01 / "admission.catalogue.yaml"
    with pytest.raises(ValueError, match="arm"):
        load_dogwood_inputs(T01, intent="goal-level", arm="L1-S")      # not a file arm: L1 + --input-mode schema-only


def test_build_writes_the_2c_arms_next_to_the_2b_arms(tmp_path):
    rec = build_arms.build(tmp_path / "arms")
    assert set(rec["arms"]) == {"v2", "typed", "L1", "L2", "L3", "L4"}        # the 2b record is what build() returns, unchanged
    assert (tmp_path / "arms" / "arms.json").read_bytes() == (ARMS / "arms.json").read_bytes()
    assert (tmp_path / "arms" / "arms-2c.json").read_bytes() == (ARMS / "arms-2c.json").read_bytes()


# ---- L7 mirror-marker
def test_L7_is_L3s_vendor_entry_with_the_marker_enum_lists(rec):
    l3 = _json(ARMS / "L3" / "manifests" / "wo.tools.json")
    tool = next(t for t in l3["tools"] if t["name"] == "get_approval_record")
    tool["outputSchema"]["properties"]["decision"]["enum"] = MARKER_OUTCOMES
    tool["outputSchema"]["properties"]["approver_kind"]["enum"] = MARKER_KINDS
    assert _dump(l3) == (ARMS / "L7" / "manifests" / "wo.tools.json").read_text()
    e = rec["arms"]["L7"]
    assert e["vendor_edit"]["tool_name"] == "get_approval_record"
    assert e["vendor_edit"]["output_fields"]["decision"]["enum"] == MARKER_OUTCOMES and e["vendor_edit"]["output_fields"]["approver_kind"]["enum"] == MARKER_KINDS
    assert e["positive"] == {"decision": "SIGNED_OFF", "approver_kind": "OPERATOR"} and e["negative"] == {"decision": "DECLINED", "approver_kind": "BOT"}
    assert e["marker_tokens"] == ["SIGNED_OFF", "OPERATOR"]
    gen = generate_dogwood([ARMS / "L7" / "manifests" / "wo.tools.json", ARMS / "v2" / "manifests" / "authority.tools.json"])
    assert gen == (ARMS / "L7" / "schema" / "t01.dogwood.generated.cedarschema").read_text()
    assert link_session_id(ARMS / "L7" / "schema" / "t01.dogwood.generated.cedarschema") == (ARMS / "L7" / "schema" / "t01.dogwood.cedarschema").read_text()
    assert 'entity get_approval_record_Output_decision enum ["SIGNED_OFF", "DECLINED", "QUEUED"];' in gen
    assert "decision: String" in gen and "approver_kind: String" in gen       # the authority stays untyped


def test_L7_suite_is_L3s_with_marker_runtime_outputs(suites):
    s, l3 = suites["L7"], suites["L3"]
    assert set(s.ids) == set(l3.ids) and {t: s.contract[t] for t in HELD_OUT} == HELD_OUT
    for tid in l3.ids:
        same = s.traces[tid].read_bytes() == l3.traces[tid].read_bytes()
        assert same == (tid not in HELD_OUT), tid
    t15 = s.traces["t15_vendor_enum_only"].read_text()
    assert 'decision: Drupe::get_approval_record_Output_decision::"SIGNED_OFF"' in t15
    assert 'approver_kind: Drupe::get_approval_record_Output_approver_kind::"OPERATOR"' in t15 and "authority_get_approval" not in t15
    t17 = s.traces["t17_authority_granted_vendor_negative"].read_text()
    assert '"DECLINED"' in t17 and '"BOT"' in t17 and 'decision: "GRANTED"' in t17
    assert "GRANTED" not in t15 and "HUMAN" not in t15


# ---- L5 defended
def test_L5_is_typed_authority_plus_L2_vendor_with_typed_gold(rec):
    assert not (ARMS / "L5" / "manifests").exists()      # L5 names L2's vendor file and typed's authority file; no copies
    gen = generate_dogwood([ARMS / "L2" / "manifests" / "wo.tools.json", ARMS / "typed" / "manifests" / "authority.tools.json"])
    assert gen == (ARMS / "L5" / "schema" / "t01.dogwood.generated.cedarschema").read_text()
    assert link_session_id(ARMS / "L5" / "schema" / "t01.dogwood.generated.cedarschema") == (ARMS / "L5" / "schema" / "t01.dogwood.cedarschema").read_text()
    assert 'entity authority_get_approval_Output_decision enum ["GRANTED", "REJECTED", "PENDING"];' in gen
    assert 'entity get_workorder_Output_approval_outcome enum ["SIGNED_OFF", "DECLINED", "QUEUED"];' in gen
    assert (ARMS / "L5" / "gold.dw").read_bytes() == (ARMS / "typed" / "gold.dw").read_bytes()
    assert rec["arms"]["L5"]["condition"] == "defense" and "trusted input" in rec["arms"]["L5"]["note"]


def test_L5_suite_is_the_typed_suite_plus_L2s_held_out_traces_with_typed_authority_events(suites):
    s, typed, l2 = suites["L5"], suites["typed"], suites["L2"]
    assert set(s.ids) == set(typed.ids) | set(HELD_OUT) and {t: s.contract[t] for t in HELD_OUT} == HELD_OUT
    for tid in typed.ids:
        assert s.traces[tid].read_bytes() == typed.traces[tid].read_bytes(), tid
    assert s.traces["t15_vendor_enum_only"].read_bytes() == l2.traces["t15_vendor_enum_only"].read_bytes()
    ent = re.compile(r'(decision|approver_kind): Drupe::authority_get_approval_Output_\1::("[A-Z]+")')
    for tid in ("t16_authority_rejected_vendor_positive", "t17_authority_granted_vendor_negative"):
        mine, theirs = s.traces[tid].read_text(), l2.traces[tid].read_text()
        assert mine != theirs and ent.sub(r"\1: \2", mine) == theirs, tid
        assert "Drupe::get_workorder_Output_approval_outcome::" in mine


def test_L5_borrowed_literal_mutant_is_killed_by_validation_not_by_a_trace(rec):
    """Marker values on a typed authority predicate are not members of the enum: strict validation rejects the mutant
    (the defense), so it has no allow-set. Recorded as killed_by_validation; the admission checker rejects it by text."""
    e = rec["arms"]["L5"]["mutants"]["borrowed_literal"]
    r = temporal.check(ARMS / "L5" / "mutants" / "borrowed_literal.dw", ARMS / "L5" / "schema" / "t01.dogwood.cedarschema", EVENTS)
    assert r.ok is False and any("not one of its permitted ids" in m for m in r.errors)
    assert e["killed_by"] == [] and e["killed_by_validation"] is True and "not one of its permitted ids" in e["validation_error"]


# ---- L6 undeclared
def test_L6_is_L1s_vendor_entry_without_the_enums(rec):
    l1 = _json(ARMS / "L1" / "manifests" / "wo.tools.json")
    tool = next(t for t in l1["tools"] if t["name"] == "get_workorder")
    for f in ("approval_outcome", "approver_type"):
        del tool["outputSchema"]["properties"][f]["enum"]
    assert _dump(l1) == (ARMS / "L6" / "manifests" / "wo.tools.json").read_text()
    e = rec["arms"]["L6"]
    assert e["vendor_edit"]["output_fields"] == {"approval_outcome": {"title": "Approval Outcome", "type": "string"},
                                                 "approver_type": {"title": "Approver Type", "type": "string"}}
    gen = generate_dogwood([ARMS / "L6" / "manifests" / "wo.tools.json", ARMS / "v2" / "manifests" / "authority.tools.json"])
    assert gen == (ARMS / "L6" / "schema" / "t01.dogwood.generated.cedarschema").read_text()
    assert "approval_outcome?: String" in gen and "approver_type?: String" in gen and "get_workorder_Output_approval_outcome" not in gen
    assert link_session_id(ARMS / "L6" / "schema" / "t01.dogwood.generated.cedarschema") == (ARMS / "L6" / "schema" / "t01.dogwood.cedarschema").read_text()
    assert "borrowed_literal" not in e["mutants"] and "states no value" in e["borrowed_literal_note"]


def test_L6_suite_is_L1s_with_plain_string_vendor_outputs(suites):
    s, l1 = suites["L6"], suites["L1"]
    assert set(s.ids) == set(l1.ids) and {t: s.contract[t] for t in HELD_OUT} == HELD_OUT
    for tid in l1.ids:
        assert (s.traces[tid].read_bytes() == l1.traces[tid].read_bytes()) == (tid not in HELD_OUT), tid
    t15 = s.traces["t15_vendor_enum_only"].read_text()
    assert 'approval_outcome: "GRANTED"' in t15 and 'approver_type: "HUMAN"' in t15 and "_Output_approval_outcome::" not in t15
    assert 'approval_outcome: "REJECTED"' in s.traces["t17_authority_granted_vendor_negative"].read_text()


# ---- all 2c arms: gold = contract, mutants killed, requirements
@pytest.mark.parametrize("arm", ["L7", "L5", "L6"])
def test_gold_agrees_with_the_contract_on_every_trace(arm, suites):
    inp = load_dogwood_inputs(T01, intent="goal-level", arm=arm)
    s = suites[arm]
    assert temporal.check(inp.gold, inp.schema_path, EVENTS).ok
    assert temporal.allowed(inp.gold, s, inp.schema_path, EVENTS) == {t for t, w in s.contract.items() if w}


@pytest.mark.parametrize("arm", ["L7", "L5", "L6"])
def test_every_mutant_is_killed_as_recorded(arm, rec, suites):
    s, schema = suites[arm], ARMS / arm / "schema" / "t01.dogwood.cedarschema"
    contract = {t for t, w in s.contract.items() if w}
    for name, info in rec["arms"][arm]["mutants"].items():
        p = ARMS / arm / "mutants" / f"{name}.dw"
        assert p.is_file(), (arm, name)
        if info.get("killed_by_validation"):
            assert not temporal.check(p, schema, EVENTS).ok
            continue
        assert temporal.check(p, schema, EVENTS).ok, (arm, name)
        killed = temporal.allowed(p, s, schema, EVENTS) ^ contract
        assert killed and sorted(killed) == info["killed_by"], (arm, name)
    vb = ARMS / arm / "mutants" / "vendor_binding.dw"
    assert temporal.decision(vb, schema, s.traces["t15_vendor_enum_only"], EVENTS) is True     # the vendor events are live
    assert temporal.decision(vb, schema, s.traces["t17_authority_granted_vendor_negative"], EVENTS) is False
    assert temporal.decision(vb, schema, s.traces["t08_vendor_flag_only"], EVENTS) is False


def test_borrowed_literal_mutants_exist_for_L7_and_L5_only(rec):
    assert {a for a, e in rec["arms"].items() if "borrowed_literal" in e["mutants"]} == {"L7", "L5"}
    assert all("vendor_binding" in e["mutants"] for e in rec["arms"].values())
    assert rec["arms"]["L7"]["mutants"]["borrowed_literal"]["killed_by"] == ["t01_valid", "t12_second_close_same_session", "t13_other_wo_valid",
                                                                              "t17_authority_granted_vendor_negative"]


@pytest.mark.parametrize("arm,vendor_action,stated,approver_fields", [
    ("L7", "get_approval_record", MARKER_OUTCOMES + MARKER_KINDS, ["output.approver_kind"]),
    ("L5", "get_workorder", MARKER_OUTCOMES + MARKER_KINDS, ["output.approver_kind", "output.approver_type"]),
    ("L6", "get_workorder", [], ["output.approver_kind", "output.approver_type"]),
])
def test_requirements_vocabulary_and_vendor_only_traces(arm, vendor_action, stated, approver_fields, suites):
    reqs = load_requirements(ARMS / arm / "requirements.yaml", suites[arm])
    assert reqs.vendor_only == ("t08_vendor_flag_only", "t15_vendor_enum_only")
    assert reqs.vocabulary["vendor_actions"] == [vendor_action] and reqs.vocabulary["vendor_stated_values"] == stated
    assert reqs.vocabulary["approver_kind_fields"] == approver_fields and reqs.vocabulary["authority_action"] == "authority_get_approval"
    assert "t17_authority_granted_vendor_negative" in reqs.over_strict_if_denies and "t15_vendor_enum_only" in reqs.over_permissive_if_allows


# ---- A1 re-tally check against Phase 2b behaviour (the run folders are committed; zero API)
def _vocab_and_schema(run: Path):
    inp = load_dogwood_inputs(T01, intent="goal-level", arm=json.loads((run / "config.json").read_text())["arm"]["name"])
    reqs = load_requirements(inp.requirements, temporal.load_suite(inp.traces_yaml))
    return reqs.vocabulary, inp.schema_text


@pytest.mark.parametrize("arm", ["v2", "L1", "L2", "L3"])
def test_close_scoped_bind_agrees_with_phase_2b_behaviour(arm):
    """On every valid, scored final policy: BIND=vendor implies it allows a vendor-only trace, and allowing one implies
    BIND in {vendor, both}. TOKEN is 0 everywhere (2b: no marker token in an authority predicate)."""
    run = ROOT / "runs" / RUNS_2B[arm]
    vocab, schema = _vocab_and_schema(run)
    checked = 0
    for gen in ("naive", "sondera"):
        for d in sorted((run / "t01_close_after_approval" / gen).glob("sample_*")):
            o = json.loads((d / "oracle.json").read_text())
            r = close_binding_report((d / "policy.dw").read_text(), vocab, "close_workorder", schema)
            assert r["token"] is False and r["unresolved_scope"] is False, d
            if o["valid"] and o["scored"]:
                allows = bool(o["allows_vendor_only"])
                assert (r["bind"] == "vendor") <= allows, (d, r["bind"], o["allows_vendor_only"])
                assert allows <= (r["bind"] in ("vendor", "both")), (d, r["bind"])
                checked += 1
            if gen == "sondera":   # the first shot is round 1's text; the tally must run on invalid text too
                fs = close_binding_report((d / "round1.dw").read_text(), vocab, "close_workorder", schema)
                assert fs["bind"] in ("authority", "vendor", "both", "none")
    assert checked >= 20
