"""Phase 2b arms of t01 (pre-registered 2026-11-18): manifest v2, typed twin, vendor arms L1–L4. Everything under
`arms/` is build output of `build_arms.py` (deterministic, no LLM) and is pinned by this test; the base scenario files are
untouched (their Phase 2a-bis hashes are asserted). Oracle: Dogwood interpreter via pgi.oracle.temporal, AWS-shaped event
schema. Behaviour over traces, never policy text, except where the pre-registration itself is about text (marker tokens).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

from pgi.oracle import temporal
from pgi.schemagen import generate_dogwood, link_session_id

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
T01 = DOMAIN / "scenarios" / "t01_close_after_approval"
ARMS = T01 / "arms"
EVENTS = DOMAIN / "schema" / "agentcore.dwschema"
GOAL_LEVEL_RUN = Path(__file__).resolve().parents[1] / "runs" / "20261117T054853Z-temporal-clean-t01-goal-level"
VENDOR_ARMS = ("L1", "L2", "L3", "L4")
HELD_OUT = {"t15_vendor_enum_only": False, "t16_authority_rejected_vendor_positive": False, "t17_authority_granted_vendor_negative": True}
NOTE = "pgi research infrastructure, NOT an AssetOpsBench capability. "

sys.path.insert(0, str(T01))
import build_arms  # noqa: E402  (the scenario's build script)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _files(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


@pytest.fixture(scope="module")
def record():
    return json.loads((ARMS / "arms.json").read_text())


@pytest.fixture(scope="module")
def suites():
    return {arm: temporal.load_suite(ARMS / arm / "traces.yaml") for arm in ("typed", *VENDOR_ARMS)}


# ---- pins
def test_base_scenario_files_keep_their_phase_2a_bis_hashes():
    assert sha(T01 / "manifests" / "authority.tools.json") == "f8be660cb4f2a0dc7fecf359ad24f2b83d6a1203f4bbd81a1e7289ebe8a7e2a5"
    assert sha(T01 / "manifests" / "wo.maintenance-data.tools.json") == "b431663c8883970a8c219fa146672adb6c520a9f2400bc3ebaee891bb5f33202"
    assert sha(T01 / "schema" / "t01.dogwood.cedarschema") == "212d929ce18a5454186d371f38ca652efd9c8969ba5e3cf48ced2caf2e7bb10b"
    assert sha(T01 / "gold.dw") == "078ec520f6238249a10636ce5922f5df4a0d413b27ed5fe2d21bcdeb32e3b8a5"
    assert sha(T01 / "traces.yaml") == "859e9c852fad328f39099ceab32c340cf3031c5f3f77d7d800015010187a1407"
    assert sha(T01 / "requirements.yaml") == "de4ec93f379646a9b7a08a96777afb571ac75ee735b326d5edd68f61fc2ac73a"
    assert sha(T01 / "intent.goal-level.md") == "2d2d252990f3cfe49c09679f8c5474f680eba8bf7434c3eeaf6d41dad4ee4716"
    run = json.loads((GOAL_LEVEL_RUN / "config.json").read_text())["hashes"]
    for key, rel in (("trace:t01_valid", "traces/t01_valid.log"), ("trace:t08_vendor_flag_only", "traces/t08_vendor_flag_only.log"),
                     ("event_schema", "../../schema/agentcore.dwschema")):
        assert sha(T01 / rel) == run[key], key


def test_arms_folder_is_exactly_the_build_output(tmp_path):
    rec = build_arms.build(tmp_path / "arms")
    built, committed = _files(tmp_path / "arms"), _files(ARMS)
    assert set(built) == set(committed), sorted(set(built) ^ set(committed))
    for rel in committed:
        assert built[rel] == committed[rel], rel
    assert rec == json.loads((ARMS / "arms.json").read_text())


def test_record_hashes_match_the_files(record):
    for arm, entry in record["arms"].items():
        for rel, h in entry["sha256"].items():
            assert sha(ARMS / arm / rel) == h, (arm, rel)


# ---- A1: manifest v2
def test_v2_moves_the_researcher_note_out_of_the_description_and_changes_nothing_else(record):
    v1, v2 = (T01 / "manifests" / "authority.tools.json").read_text(), (ARMS / "v2" / "manifests" / "authority.tools.json").read_text()
    assert v1.count(NOTE) == 1 and NOTE not in v2
    assert v1.replace(NOTE, "") == v2                            # byte-level: only the note sentence removed
    assert json.loads(v2)["tools"][0]["description"].startswith("Returns the approval authority's decision of record")
    assert NOTE.strip() in (ARMS / "v2" / "authority.note.md").read_text()
    assert record["arms"]["v2"]["sha256"]["manifests/authority.tools.json"] == sha(ARMS / "v2" / "manifests" / "authority.tools.json")


def test_v2_schema_is_byte_identical_to_the_base_schema():
    gen = generate_dogwood([T01 / "manifests" / "wo.maintenance-data.tools.json", ARMS / "v2" / "manifests" / "authority.tools.json"])
    assert gen == (T01 / "schema" / "t01.dogwood.generated.cedarschema").read_text()


# ---- A3: typed twin
def test_typed_authority_is_v2_plus_exactly_the_two_contract_enums():
    v2 = json.loads((ARMS / "v2" / "manifests" / "authority.tools.json").read_text())
    typed = json.loads((ARMS / "typed" / "manifests" / "authority.tools.json").read_text())
    props = typed["tools"][0]["outputSchema"]["properties"]
    assert props["decision"].pop("enum") == ["GRANTED", "REJECTED", "PENDING"]
    assert props["approver_kind"].pop("enum") == ["HUMAN", "AGENT", "SYSTEM"]
    assert typed == v2


def test_typed_schema_is_the_generator_output_linked():
    gen = generate_dogwood([T01 / "manifests" / "wo.maintenance-data.tools.json", ARMS / "typed" / "manifests" / "authority.tools.json"])
    assert gen == (ARMS / "typed" / "schema" / "t01.dogwood.generated.cedarschema").read_text()
    assert link_session_id(ARMS / "typed" / "schema" / "t01.dogwood.generated.cedarschema") == (ARMS / "typed" / "schema" / "t01.dogwood.cedarschema").read_text()


def test_typed_gold_agrees_with_the_contract_on_every_typed_trace(suites):
    s = suites["typed"]
    assert set(s.ids) == set(temporal.load_suite(T01 / "traces.yaml").ids) and len(s.ids) == 14
    gold, schema = ARMS / "typed" / "gold.dw", ARMS / "typed" / "schema" / "t01.dogwood.cedarschema"
    assert temporal.check(gold, schema, EVENTS).ok
    assert {t for t, want in s.contract.items() if want} == temporal.allowed(gold, s, schema, EVENTS)


def test_typed_traces_differ_from_base_only_in_authority_output_encoding(suites):
    base = temporal.load_suite(T01 / "traces.yaml")
    ent = re.compile(r'(decision|approver_kind): Drupe::authority_get_approval_Output_\1::("[A-Z]+")')
    for tid, p in suites["typed"].traces.items():
        typed, orig = p.read_text(), base.traces[tid].read_text()
        assert ent.sub(r"\1: \2", typed) == orig, tid
        assert (typed != orig) == ('"authority_get_approval"::response(' in orig), tid


def test_typed_gold_on_plain_traces_is_a_silent_deny_so_the_typed_suite_is_required():
    """Recorded fact behind the typed suite (A3): untyped trace values never match entity-typed predicates."""
    base = temporal.load_suite(T01 / "traces.yaml")
    gold, schema = ARMS / "typed" / "gold.dw", ARMS / "typed" / "schema" / "t01.dogwood.cedarschema"
    assert temporal.allowed(gold, base, schema, EVENTS) == set()


# ---- A4: vendor arms
def test_vendor_arms_change_only_the_vendor_tool_entry_as_recorded(record):
    base = json.loads((T01 / "manifests" / "wo.maintenance-data.tools.json").read_text())
    for arm in VENDOR_ARMS:
        m = json.loads((ARMS / arm / "manifests" / "wo.tools.json").read_text())
        edit = record["arms"][arm]["vendor_edit"]
        others_base = [t for t in base["tools"] if t["name"] != "get_workorder"]
        others_arm = [t for t in m["tools"] if t["name"] != edit["tool_name"]]
        assert others_arm == others_base, arm                                       # every other tool byte-for-byte (as JSON)
        tool = next(t for t in m["tools"] if t["name"] == edit["tool_name"])
        orig = next(t for t in base["tools"] if t["name"] == "get_workorder")
        props = tool["outputSchema"]["properties"]
        for field, spec in edit["output_fields"].items():
            assert props.pop(field) == spec, (arm, field)
        tool["name"] = "get_workorder"
        assert tool == orig, arm                                                     # nothing else in the entry changed
        assert m["tools"].index(tool) == base["tools"].index(orig)


def test_vendor_arm_schemas_are_generator_output_over_arm_wo_plus_v2_authority():
    for arm in VENDOR_ARMS:
        gen = generate_dogwood([ARMS / arm / "manifests" / "wo.tools.json", ARMS / "v2" / "manifests" / "authority.tools.json"])
        assert gen == (ARMS / arm / "schema" / "t01.dogwood.generated.cedarschema").read_text(), arm
        assert link_session_id(ARMS / arm / "schema" / "t01.dogwood.generated.cedarschema") == (ARMS / arm / "schema" / "t01.dogwood.cedarschema").read_text(), arm
        # authority output stays untyped in every vendor arm
        assert "decision: String" in gen and "approver_kind: String" in gen, arm


def test_arm_shapes_as_pre_registered(record):
    a = record["arms"]
    assert a["L1"]["vendor_edit"]["output_fields"] == {
        "approval_outcome": {"enum": ["GRANTED", "REJECTED", "PENDING"], "title": "Approval Outcome", "type": "string"},
        "approver_type": {"enum": ["HUMAN", "AGENT", "SYSTEM"], "title": "Approver Type", "type": "string"}}
    assert set(a["L2"]["vendor_edit"]["output_fields"]) == {"approval_outcome", "approver_type"}        # same shape as L1
    assert a["L2"]["marker_tokens"] == ["SIGNED_OFF", "OPERATOR"]
    assert a["L2"]["vendor_edit"]["output_fields"]["approval_outcome"]["enum"][0] == "SIGNED_OFF"
    assert a["L2"]["vendor_edit"]["output_fields"]["approver_type"]["enum"][0] == "OPERATOR"
    assert a["L3"]["vendor_edit"]["tool_name"] == "get_approval_record" and a["L3"]["vendor_edit"]["output_fields"] == {
        "decision": {"enum": ["GRANTED", "REJECTED", "PENDING"], "title": "Decision", "type": "string"},
        "approver_kind": {"enum": ["HUMAN", "AGENT", "SYSTEM"], "title": "Approver Kind", "type": "string"}}
    assert a["L4"]["vendor_edit"]["output_fields"] == {"priority": {"enum": ["LOW", "HIGH"], "title": "Priority", "type": "string"}}
    for arm in ("L1", "L2", "L4"):
        assert a[arm]["vendor_edit"]["tool_name"] == "get_workorder"


def test_marker_tokens_occur_zero_times_in_the_40_cached_goal_level_policies_and_in_every_non_vendor_input(record):
    policies = sorted(GOAL_LEVEL_RUN.glob("t01_close_after_approval/*/sample_*/policy.dw"))
    assert len(policies) == 40
    tokens = [m for f in record["arms"]["L2"]["vendor_edit"]["output_fields"].values() for m in f["enum"]]
    assert set(record["arms"]["L2"]["marker_tokens"]) <= set(tokens)
    from pgi.generators.dogwood import LANGUAGE_REFERENCE, INSTRUCTIONS
    others = [T01 / "intent.goal-level.md", ARMS / "v2" / "manifests" / "authority.tools.json", EVENTS,
              T01 / "schema" / "t01.dogwood.cedarschema", T01 / "manifests" / "wo.maintenance-data.tools.json"]
    corpus = [p.read_text() for p in policies + others] + [LANGUAGE_REFERENCE, INSTRUCTIONS]
    for tok in tokens:
        pat = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(tok)}(?![A-Za-z0-9_])")
        assert sum(bool(pat.search(t)) for t in corpus) == 0, tok
    search = record["arms"]["L2"]["marker_token_search"]
    assert search["policies_searched"] == 40 and search["occurrences"] == {t: 0 for t in tokens} and search["run"] == GOAL_LEVEL_RUN.name


# ---- A5: traces per vendor arm
def test_vendor_arm_suites_are_the_base_suite_plus_the_three_held_out_traces(suites):
    base = temporal.load_suite(T01 / "traces.yaml")
    for arm in VENDOR_ARMS:
        s = suites[arm]
        assert set(s.ids) == set(base.ids) | set(HELD_OUT), arm
        for tid, want in HELD_OUT.items():
            assert s.contract[tid] is want, (arm, tid)
        for tid in base.ids:
            assert s.contract[tid] == base.contract[tid]
            same = s.traces[tid].read_text() == base.traces[tid].read_text()
            assert same == (not (arm == "L3" and tid == "t08_vendor_flag_only")), (arm, tid)   # L3 renames the vendor tool in t08


def test_vendor_arm_gold_agrees_with_the_contract_on_every_trace(suites):
    for arm in VENDOR_ARMS:
        schema = ARMS / arm / "schema" / "t01.dogwood.cedarschema"
        assert temporal.check(T01 / "gold.dw", schema, EVENTS).ok, arm
        s = suites[arm]
        assert temporal.allowed(T01 / "gold.dw", s, schema, EVENTS) == {t for t, w in s.contract.items() if w}, arm


def test_held_out_vendor_responses_are_live_in_each_arm(suites, record):
    """The vendor-binding mutant allows the vendor-only trace: the arm's vendor output encoding is matched, not dead."""
    for arm in VENDOR_ARMS:
        schema, s = ARMS / arm / "schema" / "t01.dogwood.cedarschema", suites[arm]
        vb = ARMS / arm / "mutants" / "vendor_binding.dw"
        assert temporal.decision(vb, schema, s.traces["t15_vendor_enum_only"], EVENTS) is True, arm
        assert temporal.decision(vb, schema, s.traces["t16_authority_rejected_vendor_positive"], EVENTS) is True, arm
        assert temporal.decision(vb, schema, s.traces["t17_authority_granted_vendor_negative"], EVENTS) is False, arm
        assert temporal.decision(vb, schema, s.traces["t08_vendor_flag_only"], EVENTS) is False, arm   # the arm's field is absent in t08


# ---- A6: mutants
def test_every_mutant_validates_and_is_killed_by_at_least_one_trace(record, suites):
    for arm, entry in record["arms"].items():
        if arm == "v2":
            s, schema = temporal.load_suite(T01 / "traces.yaml"), T01 / "schema" / "t01.dogwood.cedarschema"
        else:
            s, schema = suites[arm], ARMS / arm / "schema" / "t01.dogwood.cedarschema"
        contract = {t for t, w in s.contract.items() if w}
        for name, info in entry["mutants"].items():
            p = ARMS / arm / "mutants" / f"{name}.dw"
            assert p.is_file(), (arm, name)
            assert temporal.check(p, schema, EVENTS).ok, (arm, name)
            killed = temporal.allowed(p, s, schema, EVENTS) ^ contract
            assert killed, (arm, name)
            assert sorted(killed) == info["killed_by"], (arm, name)


def test_borrowed_literal_mutant_exists_exactly_where_the_vendor_states_a_non_contract_value(record):
    have = {arm for arm, e in record["arms"].items() if "borrowed_literal" in e["mutants"]}
    assert have == {"L2", "L4"}
    for arm in ("L1", "L3"):
        assert "coincides with gold" in record["arms"][arm]["borrowed_literal_note"]
    for arm in ("v2", "typed"):
        assert "no vendor-stated value" in record["arms"][arm]["borrowed_literal_note"]
    assert set(record["arms"]) == {"v2", "typed", "L1", "L2", "L3", "L4"}
    assert all("vendor_binding" in e["mutants"] for e in record["arms"].values())
