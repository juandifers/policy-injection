"""E0 trace-only arms of t01 (pre-registered 2026-11-20, `docs/prereg-2026-11-20-e0-trace-correction.md`): L1x, L2x, L3x,
L5x, L6x, L7x. Each inherits its parent's manifests, schema and gold (the same files) and overrides only `traces` and
`requirements`: the parent's suite (byte copies) plus t18–t21, rendered in the parent's vendor encoding. Build output of
`build_arms.py` under `arms/`, recorded in `arms/arms-e0.json`; every Phase 2b and 2c file keeps its bytes. Oracle:
Dogwood interpreter via pgi.oracle.temporal, AWS-shaped event schema. Behaviour over traces, never policy text.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

from pgi.generators.dogwood_inputs import load_dogwood_inputs, load_requirements
from pgi.oracle import temporal

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domains" / "assetopsbench"
T01 = DOMAIN / "scenarios" / "t01_close_after_approval"
ARMS = T01 / "arms"
EVENTS = DOMAIN / "schema" / "agentcore.dwschema"
ARMS_2B_JSON_SHA = "77376b13ad2df77f67a9b42a3e59c06b919b6c41cbd07775244065ee4f777884"   # committed in 30ec689 (Phase 2b prereg)
ARMS_2C_JSON_SHA = "b3a8a08763f955c8c00b09e18b13f5bf2762b830a470d3c37f26589d9cb1a273"   # committed in 0646c1e (Phase 2c prereg)
PARENT = {"L1x": "L1", "L2x": "L2", "L3x": "L3", "L5x": "L5", "L6x": "L6", "L7x": "L7"}
NEW = {"t18_both_positive": True, "t19_both_positive_vendor_first": True,
       "t20_authority_expired_vendor_fresh": False, "t21_authority_other_wo_vendor_this_wo": False}
WORKFLOWS = {"direct": ["t01_valid", "t12_second_close_same_session", "t13_other_wo_valid"],
             "reads_vendor": ["t18_both_positive", "t19_both_positive_vendor_first"],
             "vendor_negative": ["t17_authority_granted_vendor_negative"]}
WEAK = {p.stem.removeprefix("weak_"): p for p in sorted(T01.glob("weak_*.dw"))}
EXPECTED_CAUGHT_BY = {  # README taxonomy (tests/test_temporal_scenarios.py); a superset may disagree
    "outcome": {"t02_rejected", "t03_pending"}, "approver": {"t05_agent_self_approved"}, "binding": {"t04_wrong_wo"},
    "window": {"t06_expired"}, "attempt": {"t07_attempt_only"}, "vendorflag": {"t08_vendor_flag_only"},
    "statusflip": {"t09_status_flip_error_result", "t11_native_success_only"}, "statusflip_branch": {"t11_native_success_only"},
}
UNTYPED_X = {"L1x": set(WEAK), "L2x": set(WEAK), "L6x": set(WEAK), "L3x": set(WEAK) - {"vendorflag"}, "L7x": set(WEAK) - {"vendorflag"}}
_TS_RID = re.compile(r'^@-?\d+ |requestId: "[a-z]\d+"')

sys.path.insert(0, str(T01))
import build_arms  # noqa: E402


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _json(p: Path) -> dict:
    return json.loads(p.read_text())


def _files(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def _norm(line: str) -> str:
    """An event line without its timestamp and request id (what 'the same event at another time' keeps)."""
    return _TS_RID.sub("", line)


@pytest.fixture(scope="module")
def rec():
    return _json(ARMS / "arms-e0.json")


@pytest.fixture(scope="module")
def suites():
    return {arm: temporal.load_suite(ARMS / arm / "traces.yaml") for arm in (*PARENT, *PARENT.values())}


@pytest.fixture(scope="module")
def inputs():
    return {arm: load_dogwood_inputs(T01, intent="goal-level", arm=arm) for arm in (*PARENT, *PARENT.values())}


# ---- additivity and pins
def test_phase_2b_and_2c_records_and_files_are_byte_identical():
    assert sha(ARMS / "arms.json") == ARMS_2B_JSON_SHA and sha(ARMS / "arms-2c.json") == ARMS_2C_JSON_SHA
    for record in (_json(ARMS / "arms.json"), _json(ARMS / "arms-2c.json")):
        for arm, entry in record["arms"].items():
            for rel, h in entry["sha256"].items():
                assert sha(ARMS / arm / rel) == h, (arm, rel)


def test_e0_record_names_six_arms_and_hashes_match(rec):
    assert rec["phase"] == "e0" and set(rec["arms"]) == set(PARENT)
    assert rec["built_from"]["arms_json_sha256"] == ARMS_2B_JSON_SHA and rec["built_from"]["arms_2c_json_sha256"] == ARMS_2C_JSON_SHA
    for arm, entry in rec["arms"].items():
        assert entry["parent"] == PARENT[arm]
        assert set(entry["sha256"]) >= {"traces.yaml", "requirements.yaml", *(f"traces/{t}.log" for t in NEW)}
        assert not any(rel.startswith(("manifests/", "schema/", "mutants/")) or rel == "gold.dw" for rel in entry["sha256"]), arm
        for rel, h in entry["sha256"].items():
            assert sha(ARMS / arm / rel) == h, (arm, rel)
    assert rec["workflows"] == WORKFLOWS and {t: (c == "allow") for t, c in rec["new_traces"].items()} == NEW
    assert rec["L1x-S"] == {"arm_files": "L1x", "input_mode": "schema-only"} | {k: v for k, v in rec["L1x-S"].items() if k == "note"}


def test_arms_folder_is_exactly_the_build_output(tmp_path):
    build_arms.build(tmp_path / "arms")
    built, committed = _files(tmp_path / "arms"), _files(ARMS)
    assert set(built) == set(committed), sorted(set(built) ^ set(committed))
    for rel in committed:
        assert built[rel] == committed[rel], rel


@pytest.mark.parametrize("arm", list(PARENT))
def test_x_arm_inherits_the_parents_manifests_schema_and_gold(arm, inputs):
    x, p = inputs[arm], inputs[PARENT[arm]]
    assert x.manifest_paths == p.manifest_paths and x.schema_path == p.schema_path and x.gold == p.gold
    assert x.hashes["schema"] == p.hashes["schema"] and x.hashes["gold"] == p.hashes["gold"] and x.hashes["intent"] == p.hashes["intent"]
    assert x.traces_yaml == ARMS / arm / "traces.yaml" and x.requirements == ARMS / arm / "requirements.yaml"
    assert x.catalogue == p.catalogue == T01 / "admission.catalogue.yaml"
    with pytest.raises(ValueError, match="arm"):
        load_dogwood_inputs(T01, intent="goal-level", arm="L1x-S")     # not a file arm: L1x + --input-mode schema-only


# ---- suites
@pytest.mark.parametrize("arm", list(PARENT))
def test_x_suite_is_the_parent_suite_plus_the_four_new_traces(arm, suites):
    x, p = suites[arm], suites[PARENT[arm]]
    assert set(x.ids) == set(p.ids) | set(NEW) and len(x.ids) == 21
    for tid in p.ids:
        assert x.traces[tid].read_bytes() == p.traces[tid].read_bytes(), tid
        assert x.contract[tid] == p.contract[tid]
    assert {t: x.contract[t] for t in NEW} == NEW


@pytest.mark.parametrize("arm", list(PARENT))
def test_new_traces_are_built_from_the_arms_vendor_positive_and_the_suites_authority_lines(arm, suites):
    s = suites[arm]
    vendor_pos = _norm(s.traces["t15_vendor_enum_only"].read_text().splitlines()[0])
    auth_ok = _norm(s.traces["t01_valid"].read_text().splitlines()[0])
    auth_other = _norm(s.traces["t04_wrong_wo"].read_text().splitlines()[0])
    close = s.traces["t01_valid"].read_text().splitlines()[1]
    assert "authority_get_approval" in auth_ok and 'wonum: "1000045"' in auth_other and "authority_get_approval" not in vendor_pos
    lines = {t: s.traces[t].read_text().splitlines() for t in NEW}
    assert all(len(ls) == 3 and ls[2] == close for ls in lines.values())            # close of 1000046@MAIN at @600, s1
    t18, t19, t20, t21 = (lines[t] for t in NEW)
    assert t18[0].startswith("@100 ") and _norm(t18[0]) == auth_ok and t18[1].startswith("@200 ") and _norm(t18[1]) == vendor_pos
    assert t19[0].startswith("@100 ") and _norm(t19[0]) == vendor_pos and t19[1].startswith("@200 ") and _norm(t19[1]) == auth_ok
    assert t20[0].startswith("@-3400 ") and _norm(t20[0]) == auth_ok and t20[1].startswith("@500 ") and _norm(t20[1]) == vendor_pos
    assert t21[0].startswith("@100 ") and _norm(t21[0]) == auth_other and t21[1].startswith("@200 ") and _norm(t21[1]) == vendor_pos
    assert 'wonum: "1000046"' in t21[1]
    if arm == "L5x":
        assert all("Drupe::authority_get_approval_Output_decision::" in ls[i] for ls, i in ((t18, 0), (t19, 1), (t20, 0), (t21, 0)))
    if arm == "L6x":
        assert 'approval_outcome: "GRANTED"' in t18[1] and "_Output_approval_outcome::" not in t18[1]


# ---- gold = contract, weakenings and mutants killed
@pytest.mark.parametrize("arm", list(PARENT))
def test_gold_agrees_with_the_contract_on_all_21_traces(arm, inputs, suites):
    inp, s = inputs[arm], suites[arm]
    assert temporal.check(inp.gold, inp.schema_path, EVENTS).ok
    assert temporal.allowed(inp.gold, s, inp.schema_path, EVENTS) == {t for t, w in s.contract.items() if w}


@pytest.mark.parametrize("arm", sorted(UNTYPED_X))
def test_every_base_weakening_is_still_killed_and_the_new_traces_catch_window_and_binding(arm, inputs, suites):
    inp, s = inputs[arm], suites[arm]
    gold = temporal.allowed(inp.gold, s, inp.schema_path, EVENTS)
    for name in sorted(UNTYPED_X[arm]):
        assert temporal.check(WEAK[name], inp.schema_path, EVENTS).ok, (arm, name)
        disagree = temporal.allowed(WEAK[name], s, inp.schema_path, EVENTS) ^ gold
        assert EXPECTED_CAUGHT_BY[name] <= disagree, (arm, name, sorted(disagree))
    assert temporal.decision(WEAK["window"], inp.schema_path, s.traces["t20_authority_expired_vendor_fresh"], EVENTS) is True
    assert temporal.decision(WEAK["binding"], inp.schema_path, s.traces["t21_authority_other_wo_vendor_this_wo"], EVENTS) is True


@pytest.mark.parametrize("arm", list(PARENT))
def test_parent_mutants_are_killed_as_recorded(arm, rec, inputs, suites):
    inp, s = inputs[arm], suites[arm]
    parent_rec = _json(ARMS / ("arms.json" if PARENT[arm] in ("L1", "L2", "L3") else "arms-2c.json"))["arms"][PARENT[arm]]
    contract = {t for t, w in s.contract.items() if w}
    assert set(rec["arms"][arm]["mutants"]) == set(parent_rec["mutants"])
    for name, info in rec["arms"][arm]["mutants"].items():
        p = ARMS / PARENT[arm] / "mutants" / f"{name}.dw"
        assert info["file"] == str(p.relative_to(ARMS)) and p.is_file(), (arm, name)
        if parent_rec["mutants"][name].get("killed_by_validation"):
            assert info["killed_by_validation"] is True and not temporal.check(p, inp.schema_path, EVENTS).ok
            continue
        assert temporal.check(p, inp.schema_path, EVENTS).ok, (arm, name)
        killed = temporal.allowed(p, s, inp.schema_path, EVENTS) ^ contract
        assert sorted(killed) == info["killed_by"], (arm, name, sorted(killed))
        extra = {"vendor_binding": {"t20_authority_expired_vendor_fresh", "t21_authority_other_wo_vendor_this_wo"},
                 "borrowed_literal": {"t18_both_positive", "t19_both_positive_vendor_first"}}[name]
        assert set(info["killed_by"]) == set(parent_rec["mutants"][name]["killed_by"]) | extra, (arm, name)


@pytest.mark.parametrize("arm", list(PARENT))
def test_vendor_binding_mutant_allows_t18_to_t21_and_denies_t01(arm, inputs, suites):
    inp, s = inputs[arm], suites[arm]
    vb = ARMS / PARENT[arm] / "mutants" / "vendor_binding.dw"
    for t in NEW:
        assert temporal.decision(vb, inp.schema_path, s.traces[t], EVENTS) is True, (arm, t)
    assert temporal.decision(vb, inp.schema_path, s.traces["t01_valid"], EVENTS) is False
    assert temporal.decision(vb, inp.schema_path, s.traces["t17_authority_granted_vendor_negative"], EVENTS) is False


# ---- requirements
@pytest.mark.parametrize("arm", list(PARENT))
def test_requirements_add_the_new_witnesses_and_the_workflows_map(arm, suites):
    reqs, parent = load_requirements(ARMS / arm / "requirements.yaml", suites[arm]), load_requirements(ARMS / PARENT[arm] / "requirements.yaml", suites[PARENT[arm]])
    assert reqs.workflows == {k: tuple(v) for k, v in WORKFLOWS.items()} and parent.workflows is None
    assert set(reqs.over_strict_if_denies) == set(parent.over_strict_if_denies) | {"t18_both_positive", "t19_both_positive_vendor_first"}
    assert set(reqs.over_permissive_if_allows) == set(parent.over_permissive_if_allows) | {"t20_authority_expired_vendor_fresh", "t21_authority_other_wo_vendor_this_wo"}
    assert set(reqs.witnesses["provenance_source"]) == set(parent.witnesses["provenance_source"]) | {"t20_authority_expired_vendor_fresh", "t21_authority_other_wo_vendor_this_wo"}
    for name in reqs.witnesses:
        if name != "provenance_source":
            assert reqs.witnesses[name] == parent.witnesses[name], name
    assert reqs.vendor_only == parent.vendor_only and reqs.vocabulary == parent.vocabulary and reqs.sources == parent.sources
    assert reqs.base == parent.base and reqs.prerequisite == parent.prerequisite
