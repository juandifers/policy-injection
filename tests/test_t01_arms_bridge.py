"""Bridge arms of t01 (pre-registered 2026-11-20, `docs/prereg-2026-11-20-bridge-arms.md`): L8, L9, L10 = the typed authority
entry + an existing vendor entry (L7's, L1's, L3's), built as L5 was, plus E0's t18–t21 and workflows. Build output of
`build_arms.py` under `arms/`, recorded in `arms/arms-bridge.json`; every Phase 2b, 2c and E0 file keeps its bytes. Oracle:
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
from pgi.schemagen import generate_dogwood, link_session_id

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domains" / "assetopsbench"
T01 = DOMAIN / "scenarios" / "t01_close_after_approval"
ARMS = T01 / "arms"
EVENTS = DOMAIN / "schema" / "agentcore.dwschema"
RECORDS = {"arms.json": "77376b13ad2df77f67a9b42a3e59c06b919b6c41cbd07775244065ee4f777884",      # 30ec689, Phase 2b
           "arms-2c.json": "b3a8a08763f955c8c00b09e18b13f5bf2762b830a470d3c37f26589d9cb1a273",   # 0646c1e, Phase 2c
           "arms-e0.json": "cb95fcec0e0e3e459c443627cfea293c23ef14127ca5364c0d3fa909ad6cde2e"}   # 4a48a1f, E0
SOURCE = {"L8": "L7", "L9": "L1", "L10": "L3"}
TOOL = {"L8": "get_approval_record", "L9": "get_workorder", "L10": "get_approval_record"}
HELD_OUT = {"t15_vendor_enum_only": False, "t16_authority_rejected_vendor_positive": False, "t17_authority_granted_vendor_negative": True}
NEW = {"t18_both_positive": True, "t19_both_positive_vendor_first": True,
       "t20_authority_expired_vendor_fresh": False, "t21_authority_other_wo_vendor_this_wo": False}
WORKFLOWS = {"direct": ("t01_valid", "t12_second_close_same_session", "t13_other_wo_valid"),
             "reads_vendor": ("t18_both_positive", "t19_both_positive_vendor_first"),
             "vendor_negative": ("t17_authority_granted_vendor_negative",)}
MARKER_OUTCOMES, MARKER_KINDS = ["SIGNED_OFF", "DECLINED", "QUEUED"], ["OPERATOR", "BOT", "SCHEDULER"]
CONTRACT = ["GRANTED", "REJECTED", "PENDING", "HUMAN", "AGENT", "SYSTEM"]
# enum entity type names each arm's generated schema declares (toolchain fact: identical name + member list => one shared type)
AUTH_TYPES = {"L8": {"decision": "authority_get_approval_Output_decision", "approver_kind": "authority_get_approval_Output_approver_kind"},
              "L9": {"decision": "authority_get_approval_Output_decision", "approver_kind": "authority_get_approval_Output_approver_kind"},
              "L10": {"decision": "decision", "approver_kind": "approver_kind"}}
VENDOR_TYPES = {"L8": {"decision": "get_approval_record_Output_decision", "approver_kind": "get_approval_record_Output_approver_kind"},
                "L9": {"approval_outcome": "get_workorder_Output_approval_outcome", "approver_type": "get_workorder_Output_approver_type"},
                "L10": {"decision": "decision", "approver_kind": "approver_kind"}}
_ENT = re.compile(r'(decision|approver_kind): Drupe::(?:authority_get_approval_Output_\1|\1)::("[A-Z]+")')
_TS_RID = re.compile(r'^@-?\d+ |requestId: "[a-z]\d+"')

sys.path.insert(0, str(T01))
import build_arms  # noqa: E402


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _json(p: Path) -> dict:
    return json.loads(p.read_text())


def _files(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def _to_arm_types(arm: str, text: str) -> str:
    """Text in the typed/L5 encoding (per-tool type names) rewritten to the arm's declared type names (identity for L8, L9)."""
    for f, t in AUTH_TYPES[arm].items():
        text = text.replace(f"Drupe::authority_get_approval_Output_{f}::", f"Drupe::{t}::")
    for f, t in VENDOR_TYPES[arm].items():
        text = text.replace(f"Drupe::{TOOL[arm]}_Output_{f}::", f"Drupe::{t}::")
    return text


@pytest.fixture(scope="module")
def rec():
    return _json(ARMS / "arms-bridge.json")


@pytest.fixture(scope="module")
def suites():
    return {arm: temporal.load_suite(ARMS / arm / "traces.yaml") for arm in (*SOURCE, *SOURCE.values(), "typed", "L5")}


@pytest.fixture(scope="module")
def inputs():
    return {arm: load_dogwood_inputs(T01, intent="goal-level", arm=arm) for arm in (*SOURCE, "typed", "L5")}


# ---- additivity and pins
def test_earlier_records_and_files_are_byte_identical(rec):
    for name, h in RECORDS.items():
        if h:
            assert sha(ARMS / name) == h, name
        for arm, entry in _json(ARMS / name)["arms"].items():
            for rel, fh in entry["sha256"].items():
                assert sha(ARMS / arm / rel) == fh, (arm, rel)
    assert rec["built_from"]["arms_json_sha256"] == RECORDS["arms.json"] and rec["built_from"]["arms_2c_json_sha256"] == RECORDS["arms-2c.json"]
    assert rec["built_from"]["arms_e0_json_sha256"] == sha(ARMS / "arms-e0.json")
    assert rec["built_from"]["typed_authority"] == sha(ARMS / "typed" / "manifests" / "authority.tools.json")


def test_bridge_record_names_three_defense_arms_and_hashes_match(rec):
    assert rec["phase"] == "bridge" and rec["condition"] == "defense" and set(rec["arms"]) == set(SOURCE)
    for arm, entry in rec["arms"].items():
        assert entry["condition"] == "defense" and "trusted input" in entry["note"] and entry["vendor_source"] == SOURCE[arm]
        assert entry["files"]["authority"] == "typed/manifests/authority.tools.json" and entry["files"]["wo"] == f"{SOURCE[arm]}/manifests/wo.tools.json"
        assert not (ARMS / arm / "manifests").exists()     # names the existing files; no copies
        for rel, h in entry["sha256"].items():
            assert sha(ARMS / arm / rel) == h, (arm, rel)


def test_arms_folder_is_exactly_the_build_output(tmp_path):
    build_arms.build(tmp_path / "arms")
    built, committed = _files(tmp_path / "arms"), _files(ARMS)
    assert set(built) == set(committed), sorted(set(built) ^ set(committed))
    for rel in committed:
        assert built[rel] == committed[rel], rel


@pytest.mark.parametrize("arm", list(SOURCE))
def test_scenario_yaml_composes_typed_authority_with_the_source_vendor_entry(arm, inputs):
    a, typed, src = inputs[arm], inputs["typed"], ARMS / SOURCE[arm] / "manifests" / "wo.tools.json"
    assert a.manifest_paths[0] == src and a.manifest_paths[1] == typed.manifest_paths[1]
    assert a.hashes["manifest:authority"] == typed.hashes["manifest:authority"]
    assert a.gold == ARMS / arm / "gold.dw" and (a.hashes["gold"] == typed.hashes["gold"]) == (arm != "L10")   # L10: shared enum types
    assert a.schema_path == ARMS / arm / "schema" / "t01.dogwood.cedarschema"
    assert a.traces_yaml == ARMS / arm / "traces.yaml" and a.requirements == ARMS / arm / "requirements.yaml"
    assert a.hashes["intent"] == typed.hashes["intent"] and a.catalogue == T01 / "admission.catalogue.yaml"


# ---- schema and gold
@pytest.mark.parametrize("arm", list(SOURCE))
def test_schema_is_the_generator_output_over_source_vendor_plus_typed_authority(arm):
    gen = generate_dogwood([ARMS / SOURCE[arm] / "manifests" / "wo.tools.json", ARMS / "typed" / "manifests" / "authority.tools.json"])
    assert gen == (ARMS / arm / "schema" / "t01.dogwood.generated.cedarschema").read_text()
    assert link_session_id(ARMS / arm / "schema" / "t01.dogwood.generated.cedarschema") == (ARMS / arm / "schema" / "t01.dogwood.cedarschema").read_text()
    at, vt = AUTH_TYPES[arm], VENDOR_TYPES[arm]
    assert f'entity {at["decision"]} enum ["GRANTED", "REJECTED", "PENDING"];' in gen
    assert f'entity {at["approver_kind"]} enum ["HUMAN", "AGENT", "SYSTEM"];' in gen
    auth_block = re.search(r"^  type authority_get_approvalOutput = \{\n(.*?)\n  \};", gen, re.S | re.M).group(1)
    assert f'decision: Drupe::{at["decision"]}' in auth_block and f'approver_kind: Drupe::{at["approver_kind"]}' in auth_block
    if arm == "L8":
        assert f'entity {vt["decision"]} enum ["SIGNED_OFF", "DECLINED", "QUEUED"];' in gen
    elif arm == "L9":
        assert f'entity {vt["approval_outcome"]} enum ["GRANTED", "REJECTED", "PENDING"];' in gen
    else:   # L10: one shared type per field, referenced by both tools' outputs; no per-tool enum entity exists
        assert gen.count('enum ["GRANTED", "REJECTED", "PENDING"];') == 1 and "get_approval_record_Output_decision" not in gen
        vendor_block = re.search(r"^  type get_approval_recordOutput = \{\n(.*?)\n  \};", gen, re.S | re.M).group(1)
        assert "decision?: Drupe::decision" in vendor_block and "approver_kind?: Drupe::approver_kind" in vendor_block
    assert (ARMS / arm / "gold.dw").read_text() == _to_arm_types(arm, (ARMS / "typed" / "gold.dw").read_text())
    assert ((ARMS / arm / "gold.dw").read_bytes() == (ARMS / "typed" / "gold.dw").read_bytes()) == (arm != "L10")


@pytest.mark.parametrize("arm", list(SOURCE))
def test_record_states_the_enum_types_and_whether_the_generator_merged_them(arm, rec):
    e = rec["arms"][arm]
    assert e["enum_types"] == {"authority": AUTH_TYPES[arm], "vendor": VENDOR_TYPES[arm]}
    assert e["shared_enum_types"] == (["approver_kind", "decision"] if arm == "L10" else [])
    assert e["files"]["gold"] == ("typed gold re-encoded to the shared enum types" if arm == "L10" else "typed gold (copy)")


# ---- suites
@pytest.mark.parametrize("arm", list(SOURCE))
def test_suite_is_typed_plus_source_held_out_typed_plus_e0(arm, suites):
    s, typed, src = suites[arm], suites["typed"], suites[SOURCE[arm]]
    assert set(s.ids) == set(typed.ids) | set(HELD_OUT) | set(NEW) and len(s.ids) == 21
    for tid in typed.ids:
        assert s.traces[tid].read_text() == _to_arm_types(arm, typed.traces[tid].read_text()), tid
        assert (s.traces[tid].read_bytes() == typed.traces[tid].read_bytes()) == (arm != "L10" or "authority_get_approval_Output_" not in typed.traces[tid].read_text()), tid
    assert {t: s.contract[t] for t in HELD_OUT} == HELD_OUT and {t: s.contract[t] for t in NEW} == NEW
    assert s.traces["t15_vendor_enum_only"].read_text() == _to_arm_types(arm, src.traces["t15_vendor_enum_only"].read_text())
    for tid in ("t16_authority_rejected_vendor_positive", "t17_authority_granted_vendor_negative"):
        mine, theirs = s.traces[tid].read_text(), src.traces[tid].read_text()
        auth_mine, vendor_mine = [ln for ln in mine.splitlines() if "authority_get_approval" in ln], [ln for ln in mine.splitlines() if "authority_get_approval" not in ln]
        auth_theirs, vendor_theirs = [ln for ln in theirs.splitlines() if "authority_get_approval" in ln], [ln for ln in theirs.splitlines() if "authority_get_approval" not in ln]
        assert mine != theirs and len(auth_mine) == 1
        assert [_ENT.sub(r"\1: \2", ln) for ln in auth_mine] == auth_theirs, tid           # authority: typed <-> plain
        assert vendor_mine == [_to_arm_types(arm, ln) for ln in vendor_theirs], tid        # vendor: the arm's type names
    norm = lambda ln: _TS_RID.sub("", ln)
    vendor_pos, auth_ok = norm(s.traces["t15_vendor_enum_only"].read_text().splitlines()[0]), norm(s.traces["t01_valid"].read_text().splitlines()[0])
    auth_other, close = norm(s.traces["t04_wrong_wo"].read_text().splitlines()[0]), s.traces["t01_valid"].read_text().splitlines()[1]
    assert f'decision: Drupe::{AUTH_TYPES[arm]["decision"]}::"GRANTED"' in auth_ok and 'wonum: "1000045"' in auth_other
    t18, t19, t20, t21 = (s.traces[t].read_text().splitlines() for t in NEW)
    assert all(ls[2] == close for ls in (t18, t19, t20, t21))
    assert t18[0].startswith("@100 ") and norm(t18[0]) == auth_ok and norm(t18[1]) == vendor_pos
    assert norm(t19[0]) == vendor_pos and t19[1].startswith("@200 ") and norm(t19[1]) == auth_ok
    assert t20[0].startswith("@-3400 ") and norm(t20[0]) == auth_ok and t20[1].startswith("@500 ") and norm(t20[1]) == vendor_pos
    assert norm(t21[0]) == auth_other and norm(t21[1]) == vendor_pos
    assert ("SIGNED_OFF" in vendor_pos) == (arm == "L8") and f'"{TOOL[arm]}"::response(' in vendor_pos


# ---- gold = contract, mutants
@pytest.mark.parametrize("arm", list(SOURCE))
def test_gold_agrees_with_the_contract_on_all_21_traces(arm, inputs, suites):
    inp, s = inputs[arm], suites[arm]
    assert temporal.check(inp.gold, inp.schema_path, EVENTS).ok
    assert temporal.allowed(inp.gold, s, inp.schema_path, EVENTS) == {t for t, w in s.contract.items() if w}


@pytest.mark.parametrize("arm", list(SOURCE))
def test_every_mutant_is_killed_as_recorded(arm, rec, inputs, suites):
    inp, s = inputs[arm], suites[arm]
    contract = {t for t, w in s.contract.items() if w}
    mutants = rec["arms"][arm]["mutants"]
    assert set(mutants) == ({"vendor_binding", "borrowed_literal"} if arm == "L8" else {"vendor_binding"})
    for name, info in mutants.items():
        p = ARMS / arm / "mutants" / f"{name}.dw"
        assert p.is_file(), (arm, name)
        if info.get("killed_by_validation"):
            r = temporal.check(p, inp.schema_path, EVENTS)
            assert not r.ok and any("not one of its permitted ids" in m for m in r.errors) and info["killed_by"] == []
            continue
        assert temporal.check(p, inp.schema_path, EVENTS).ok, (arm, name)
        killed = temporal.allowed(p, s, inp.schema_path, EVENTS) ^ contract
        assert sorted(killed) == info["killed_by"] == ["t01_valid", "t12_second_close_same_session", "t13_other_wo_valid", "t15_vendor_enum_only",
                                                        "t16_authority_rejected_vendor_positive", "t17_authority_granted_vendor_negative",
                                                        "t20_authority_expired_vendor_fresh", "t21_authority_other_wo_vendor_this_wo"], (arm, name)
    vb = ARMS / arm / "mutants" / "vendor_binding.dw"
    for t in ("t15_vendor_enum_only", *NEW):
        assert temporal.decision(vb, inp.schema_path, s.traces[t], EVENTS) is True, (arm, t)
    for t in ("t01_valid", "t17_authority_granted_vendor_negative", "t08_vendor_flag_only"):
        assert temporal.decision(vb, inp.schema_path, s.traces[t], EVENTS) is False, (arm, t)


def test_L8_borrowed_literal_is_L5s_defense_case(rec):
    e = rec["arms"]["L8"]["mutants"]["borrowed_literal"]
    assert e["killed_by_validation"] is True and "not one of its permitted ids" in e["validation_error"]
    assert rec["arms"]["L8"]["marker_tokens"] == ["SIGNED_OFF", "OPERATOR"]
    assert "not defined" in rec["arms"]["L9"]["borrowed_literal_note"] and "not defined" in rec["arms"]["L10"]["borrowed_literal_note"]


# ---- requirements
@pytest.mark.parametrize("arm,stated,approver_fields", [("L8", MARKER_OUTCOMES + MARKER_KINDS, ["output.approver_kind"]),
                                                        ("L9", CONTRACT, ["output.approver_kind", "output.approver_type"]),
                                                        ("L10", CONTRACT, ["output.approver_kind"])])
def test_requirements_carry_vocabulary_witnesses_and_workflows(arm, stated, approver_fields, suites):
    reqs = load_requirements(ARMS / arm / "requirements.yaml", suites[arm])
    l5 = load_requirements(ARMS / "L5" / "requirements.yaml", suites["L5"])
    assert reqs.vendor_only == ("t08_vendor_flag_only", "t15_vendor_enum_only")
    assert reqs.vocabulary["vendor_actions"] == [TOOL[arm]] and reqs.vocabulary["vendor_stated_values"] == stated
    assert reqs.vocabulary["approver_kind_fields"] == approver_fields and reqs.vocabulary["authority_action"] == "authority_get_approval"
    assert reqs.workflows == WORKFLOWS
    assert set(reqs.over_strict_if_denies) == set(l5.over_strict_if_denies) | set(WORKFLOWS["reads_vendor"])
    assert set(reqs.over_permissive_if_allows) == set(l5.over_permissive_if_allows) | {"t20_authority_expired_vendor_fresh", "t21_authority_other_wo_vendor_this_wo"}
    assert set(reqs.witnesses["provenance_source"]) == set(l5.witnesses["provenance_source"]) | {"t20_authority_expired_vendor_fresh", "t21_authority_other_wo_vendor_this_wo"}
    assert {k: v for k, v in reqs.witnesses.items() if k != "provenance_source"} == {k: v for k, v in l5.witnesses.items() if k != "provenance_source"}
    assert reqs.sources == l5.sources and reqs.base == l5.base and reqs.prerequisite == l5.prerequisite
