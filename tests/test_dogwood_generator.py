"""Dogwood generators (temporal track): inputs from scenario.yaml, deterministic prompt with the language reference, the
action schema, the event schema and the manifests as the static prefix and the intent last; validation-only critic; judge;
bounded regeneration. A parallel path: the Cedar generators and their prompts are untouched (checked)."""

from pathlib import Path

import pytest

from pgi.generators import naive
from pgi.generators.dogwood import (FINAL_LINE, JUDGE_PASS, LANGUAGE_REFERENCE, NaiveDogwoodConfig, SonderaDogwoodConfig,
                                    build_request, deterministic_critique, extract_policy, generate, has_policy,
                                    judge_request, run)
from pgi.generators.dogwood_inputs import SnapshotError, load_dogwood_inputs, load_requirements, load_snapshot, snapshot
from pgi.generators.inputs import load_scenario_inputs
from pgi.llm.cache import CachedLLM
from pgi.oracle import temporal

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
T01 = DOMAIN / "scenarios" / "t01_close_after_approval"
S01 = DOMAIN / "scenarios" / "s01_close_after_approval"
GOLD = (T01 / "gold.dw").read_text()
WEAK = (T01 / "weak_outcome.dw").read_text()


class ScriptedProvider:
    """Generation and judge replies from two queues; records every request (judge = 'policy reviewer' in system[0])."""

    name = "scripted"

    def __init__(self, generations, judgements=()):
        self.generations, self.judgements, self.seen = list(generations), list(judgements), []

    def call(self, model, messages, temperature, params):
        is_judge = "policy reviewer" in params["system"][0]["text"]
        self.seen.append(("judge" if is_judge else "gen", messages, params, temperature))
        text = (self.judgements if is_judge else self.generations).pop(0)
        return {"model": model, "content": [{"type": "text", "text": text}], "usage": {}}

    def text(self, raw):
        return raw["content"][0]["text"]

    def model_version(self, raw):
        return raw["model"]

    def usage(self, raw):
        return raw["usage"]


# ---- inputs
def test_inputs_are_what_scenario_yaml_names():
    inp = load_dogwood_inputs(T01)
    assert inp.servers == ("wo", "authority")
    assert [p.name for p in inp.manifest_paths] == ["wo.maintenance-data.tools.json", "authority.tools.json"]
    assert inp.schema_path == T01 / "schema" / "t01.dogwood.cedarschema" and inp.event_schema_path == DOMAIN / "schema" / "agentcore.dwschema"
    assert inp.intent == (T01 / "intent.md").read_text() and inp.gold == T01 / "gold.dw"
    assert {"scenario_yaml", "intent", "gold", "traces_yaml", "schema", "event_schema", "manifest:wo", "manifest:authority",
            "requirements", "trace:t01_valid", "trace:t14_other_session"} <= set(inp.hashes)


def test_goal_level_intent_is_selectable_and_names_no_evidence_candidate():
    control, goal = load_dogwood_inputs(T01), load_dogwood_inputs(T01, intent="goal-level")
    assert control.intent_name == "explicit" and control.intent_path.name == "intent.md"
    assert goal.intent_name == "goal-level" and goal.intent_path.name == "intent.goal-level.md"
    assert goal.intent != control.intent and goal.hashes["intent"] != control.hashes["intent"]
    assert {k: v for k, v in goal.hashes.items() if k != "intent"} == {k: v for k, v in control.hashes.items() if k != "intent"}
    low = goal.intent.lower()
    for word in ("authority", "vendor", "approve_workorder", "get_workorder", "granted", "human", "decision of record", "approver_kind"):
        assert word not in low, word
    with pytest.raises(ValueError, match="nope"):
        load_dogwood_inputs(T01, intent="nope")


def test_cedar_scenario_is_refused():
    with pytest.raises(ValueError, match="track"):
        load_dogwood_inputs(S01)


def test_requirements_witnesses_are_contract_deny_traces_and_gold_denies_them():
    inp = load_dogwood_inputs(T01)
    suite = temporal.load_suite(inp.traces_yaml)
    reqs = load_requirements(inp.requirements, suite)
    assert reqs.base == "t01_valid" and suite.contract[reqs.base] is True
    assert set(reqs.witnesses) == {"outcome", "approver", "binding", "window", "session", "provenance_kind", "provenance_source"}
    gold_allowed = temporal.allowed(inp.gold, suite, inp.schema_path, inp.event_schema_path)
    for name, traces in reqs.witnesses.items():
        for tid in traces:
            assert suite.contract[tid] is False and tid not in gold_allowed, (name, tid)


def test_requirements_security_witnesses_sources_and_prerequisite():
    inp = load_dogwood_inputs(T01)
    suite = temporal.load_suite(inp.traces_yaml)
    reqs = load_requirements(inp.requirements, suite)
    assert all(suite.contract[t] is False for t in reqs.over_permissive_if_allows)
    assert all(suite.contract[t] is True for t in reqs.over_strict_if_denies)
    assert set(reqs.sources) == {"authority", "vendor_flag", "native_approve", "no_evidence"}
    assert reqs.sources["authority"] == reqs.base
    assert reqs.prerequisite == ("t07_attempt_only", 0)


def test_requirements_rejects_unknown_traces(tmp_path):
    inp = load_dogwood_inputs(T01)
    suite = temporal.load_suite(inp.traces_yaml)
    bad = tmp_path / "r.yaml"
    bad.write_text("base: t01_valid\nrequirements:\n  x: {requirement: 1, witnesses: [nope]}\n")
    with pytest.raises(ValueError, match="nope"):
        load_requirements(bad, suite)


def test_snapshot_round_trips_and_detects_edits(tmp_path):
    inp = load_dogwood_inputs(T01)
    snap = snapshot(inp, tmp_path / "snap")
    assert snap.hashes == inp.hashes and snap.folder == tmp_path / "snap"
    assert snap.schema_text == inp.schema_text and snap.intent == inp.intent
    assert temporal.load_suite(snap.traces_yaml).ids == temporal.load_suite(inp.traces_yaml).ids
    assert load_snapshot(tmp_path / "snap").hashes == inp.hashes
    goal = snapshot(load_dogwood_inputs(T01, intent="goal-level"), tmp_path / "snap2")
    assert goal.intent_name == "goal-level" and load_snapshot(tmp_path / "snap2").intent == goal.intent
    (tmp_path / "snap" / "intent.md").write_text("edited")
    with pytest.raises(SnapshotError, match="intent"):
        load_snapshot(tmp_path / "snap")


# ---- naive request
def test_request_layout_static_prefix_then_intent_last():
    inp = load_dogwood_inputs(T01)
    messages, params = build_request(inp, NaiveDogwoodConfig(model="m"))
    system = params["system"]
    assert [b.get("cache_control") for b in system][:-1] == [None] * (len(system) - 1)
    assert system[-1]["cache_control"] == {"type": "ephemeral"}
    static = "".join(b["text"] for b in system)
    assert LANGUAGE_REFERENCE in static and inp.schema_text in static and inp.event_schema_text in static
    for p in inp.manifest_paths:
        assert p.read_text() in static  # raw bytes of what the generator sees
    assert inp.intent not in static and "gold" not in static.lower().replace("golden", "")
    assert len(messages) == 1 and messages[0]["role"] == "user"
    assert messages[0]["content"].startswith(inp.intent) and messages[0]["content"].endswith(FINAL_LINE)
    assert FINAL_LINE == "Output only Dogwood policies."
    assert params["thinking"] == {"type": "adaptive"} and params["output_config"] == {"effort": "high"}
    assert "temperature" not in params


def test_request_is_deterministic():
    assert build_request(load_dogwood_inputs(T01), NaiveDogwoodConfig(model="m")) == \
        build_request(load_dogwood_inputs(T01), NaiveDogwoodConfig(model="m"))


def test_include_descriptions_off_changes_only_the_manifest_block():
    inp = load_dogwood_inputs(T01)
    on = build_request(inp, NaiveDogwoodConfig(model="m"))[1]["system"]
    off = build_request(inp, NaiveDogwoodConfig(model="m", include_descriptions=False))[1]["system"]
    assert on[:-1] == off[:-1] and on[-1] != off[-1]
    assert "decision of record" in on[-1]["text"] and "decision of record" not in off[-1]["text"]


def test_cedar_generators_are_untouched():
    assert naive.FINAL_LINE == "Output only Cedar policies."
    _, params = naive.build_request(load_scenario_inputs(S01), naive.NaiveConfig(model="m"))
    assert "Dogwood" not in "".join(b["text"] for b in params["system"])


@pytest.mark.parametrize("text,policy,method", [
    ("```dogwood\npermit (principal, action, resource);\n```", "permit (principal, action, resource);", "fenced"),
    ("```dw\nA;\n```\nand\n```\nB;\n```", "A;\n\nB;", "fenced"),
    ("permit (principal, action, resource);", "permit (principal, action, resource);", "raw"),
])
def test_extract_policy(text, policy, method):
    assert extract_policy(text) == (policy, method)


@pytest.mark.parametrize("text,expected", [("", False), ("// just a comment\n", False), (GOLD, True),
                                           ("forbid (principal, action, resource);", True), ("I cannot write that.", False)])
def test_has_policy(text, expected):
    assert has_policy(text) is expected


def test_invalid_output_is_returned_once_never_retried(tmp_path):
    provider = ScriptedProvider(["I cannot write that policy.", GOLD])
    sample = generate(CachedLLM(provider, tmp_path), load_dogwood_inputs(T01), NaiveDogwoodConfig(model="m"), sample_index=0)
    assert len(provider.seen) == 1 and provider.seen[0][3] is None
    assert sample.policy_text == "I cannot write that policy." and sample.extraction == "raw"


# ---- deterministic critic (validation only: no symbolic backend for Dogwood)
def write(tmp_path, text, name="p.dw"):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_gold_passes_the_critic(tmp_path):
    inp = load_dogwood_inputs(T01)
    c = deterministic_critique(write(tmp_path, GOLD), inp.schema_path, inp.event_schema_path)
    assert c.passed and c.validation.ok and not c.failures and c.feedback() == "All automated checks passed."


@pytest.mark.parametrize("text,needle", [
    ("not dogwood at all", "invalid"),
    ("", "empty"),
    ("// nothing but a comment", "empty"),
    ('permit (principal, action == Drupe::Action::"close_workorder", resource)\nwhen temporal {\n'
     '  formerly within 1h Drupe::Action::"authority_get_approval"::response{ eventResource: resource, output.nope: "x" } };', "nope"),
])
def test_critic_fails_invalid_and_empty_policy_sets(tmp_path, text, needle):
    inp = load_dogwood_inputs(T01)
    c = deterministic_critique(write(tmp_path, text), inp.schema_path, inp.event_schema_path)
    assert not c.passed and any(needle in f for f in c.failures), c.failures


# ---- judge
def test_judge_sees_intent_policy_and_language_but_not_manifests_by_default():
    inp = load_dogwood_inputs(T01)
    msgs, params = judge_request(inp, GOLD, SonderaDogwoodConfig(model="m"))
    assert "policy reviewer" in params["system"][0]["text"]
    text = "".join(b["text"] for b in params["system"]) + msgs[0]["content"]
    assert inp.intent in text and GOLD in text and LANGUAGE_REFERENCE in text and inp.event_schema_text in text
    assert "authority_get_approvalArguments" not in text
    _, p2 = judge_request(inp, GOLD, SonderaDogwoodConfig(model="m", judge_sees_manifests=True))
    assert "authority_get_approvalArguments" in "".join(b["text"] for b in p2["system"])


# ---- loop
def test_round_one_is_the_naive_request(tmp_path):
    inp = load_dogwood_inputs(T01)
    provider = ScriptedProvider([GOLD], [JUDGE_PASS])
    res = run(CachedLLM(provider, tmp_path / "cache"), inp, SonderaDogwoodConfig(model="m"), 0, tmp_path / "work")
    _, messages, params, _ = provider.seen[0]
    assert (messages, params) == build_request(inp, NaiveDogwoodConfig(model="m"))
    assert res.passed and res.rounds_used == 1 and (tmp_path / "work" / "round1.dw").read_text().strip() == GOLD.strip()


def test_regenerates_on_failure_then_stops_when_both_critics_pass(tmp_path):
    provider = ScriptedProvider(["not dogwood at all", GOLD], ["- wrong", JUDGE_PASS])
    res = run(CachedLLM(provider, tmp_path / "cache"), load_dogwood_inputs(T01), SonderaDogwoodConfig(model="m"), 0, tmp_path / "work")
    assert res.passed and res.rounds_used == 2 and res.final_policy == GOLD.strip()
    feedback = [m for kind, m, _, _ in provider.seen if kind == "gen"][1][0]["content"]
    assert "not dogwood at all" in feedback and "- wrong" in feedback and feedback.endswith(FINAL_LINE)


def test_judge_rejection_alone_forces_a_new_round(tmp_path):
    provider = ScriptedProvider([WEAK, GOLD], ["- the decision need not be GRANTED", JUDGE_PASS])
    res = run(CachedLLM(provider, tmp_path / "cache"), load_dogwood_inputs(T01), SonderaDogwoodConfig(model="m"), 0, tmp_path / "work")
    assert res.rounds_used == 2 and res.rounds[0].deterministic.passed and not res.rounds[0].judge_passed


def test_gives_up_after_max_rounds_and_keeps_the_last_attempt(tmp_path):
    provider = ScriptedProvider(["bad 1", "bad 2", "bad 3"], ["- x", "- y", "- z"])
    res = run(CachedLLM(provider, tmp_path / "cache"), load_dogwood_inputs(T01), SonderaDogwoodConfig(model="m"), 0, tmp_path / "work")
    assert not res.passed and res.rounds_used == 3 and res.final_policy == "bad 3"
    assert sorted(p.name for p in (tmp_path / "work").glob("round*.dw")) == ["round1.dw", "round2.dw", "round3.dw"]


# ---- Phase 2b: manifest arms (scenario.yaml `arms`, CLI --arm). Base inputs unchanged; each arm overrides named files.
ARMS = T01 / "arms"


def test_base_inputs_are_unchanged_by_the_arms_mechanism():
    base = load_dogwood_inputs(T01, intent="goal-level")
    assert base.arm_name == "base"
    assert base.manifest_paths == (T01 / "manifests" / "wo.maintenance-data.tools.json", T01 / "manifests" / "authority.tools.json")
    assert base.schema_path == T01 / "schema" / "t01.dogwood.cedarschema" and base.gold == T01 / "gold.dw"
    assert base.traces_yaml == T01 / "traces.yaml" and base.requirements == T01 / "requirements.yaml"
    assert base.hashes["manifest:authority"] == "f8be660cb4f2a0dc7fecf359ad24f2b83d6a1203f4bbd81a1e7289ebe8a7e2a5"  # Phase 2a-bis


def test_v2_arm_differs_from_base_in_exactly_the_authority_manifest_and_requirements():
    base, v2 = load_dogwood_inputs(T01, intent="goal-level"), load_dogwood_inputs(T01, intent="goal-level", arm="v2")
    assert v2.arm_name == "v2" and v2.intent_name == "goal-level" and v2.intent == base.intent
    changed = {k for k in base.hashes if base.hashes[k] != v2.hashes[k]}
    assert changed == {"manifest:authority", "requirements"}
    assert set(v2.hashes) == set(base.hashes)
    assert v2.manifest_paths[1] == ARMS / "v2" / "manifests" / "authority.tools.json"
    assert v2.schema_path == base.schema_path and v2.gold == base.gold and v2.traces_yaml == base.traces_yaml


def test_vendor_arms_share_the_v2_authority_file_and_override_wo_schema_traces_requirements():
    v2 = load_dogwood_inputs(T01, intent="goal-level", arm="v2")
    for arm in ("L1", "L2", "L3", "L4"):
        a = load_dogwood_inputs(T01, intent="goal-level", arm=arm)
        assert a.manifest_paths[1] == v2.manifest_paths[1] and a.hashes["manifest:authority"] == v2.hashes["manifest:authority"]
        assert a.manifest_paths[0] == ARMS / arm / "manifests" / "wo.tools.json"
        assert a.schema_path == ARMS / arm / "schema" / "t01.dogwood.cedarschema"
        assert a.traces_yaml == ARMS / arm / "traces.yaml" and a.requirements == ARMS / arm / "requirements.yaml"
        assert a.gold == v2.gold and a.hashes["gold"] == v2.hashes["gold"] and a.hashes["intent"] == v2.hashes["intent"]
        assert {"trace:t15_vendor_enum_only", "trace:t16_authority_rejected_vendor_positive", "trace:t17_authority_granted_vendor_negative"} <= set(a.hashes)


def test_typed_arm_overrides_authority_schema_gold_traces_requirements():
    v2, t = load_dogwood_inputs(T01, intent="goal-level", arm="v2"), load_dogwood_inputs(T01, intent="goal-level", arm="typed")
    assert t.manifest_paths[0] == v2.manifest_paths[0] and t.manifest_paths[1] == ARMS / "typed" / "manifests" / "authority.tools.json"
    assert t.schema_path == ARMS / "typed" / "schema" / "t01.dogwood.cedarschema" and t.gold == ARMS / "typed" / "gold.dw"
    assert t.traces_yaml == ARMS / "typed" / "traces.yaml"
    assert set(k for k in t.hashes if k.startswith("trace:")) == set(k for k in v2.hashes if k.startswith("trace:"))  # same 14 ids


def test_unknown_arm_is_refused():
    with pytest.raises(ValueError, match="arm"):
        load_dogwood_inputs(T01, intent="goal-level", arm="L9")


def test_snapshot_records_the_arm_and_round_trips(tmp_path):
    a = load_dogwood_inputs(T01, intent="goal-level", arm="L2")
    snap = snapshot(a, tmp_path / "s")
    assert snap.arm_name == "L2" and snap.hashes == a.hashes
    assert load_snapshot(tmp_path / "s").arm_name == "L2"
    assert (tmp_path / "s" / "traces" / "t15_vendor_enum_only.log").is_file()


def test_arm_requirements_carry_vendor_only_traces_and_vocabulary():
    a = load_dogwood_inputs(T01, intent="goal-level", arm="L2")
    suite = temporal.load_suite(a.traces_yaml)
    reqs = load_requirements(a.requirements, suite)
    assert reqs.vendor_only == ("t08_vendor_flag_only", "t15_vendor_enum_only")
    assert all(suite.contract[t] is False for t in reqs.vendor_only)
    assert reqs.vocabulary["authority_action"] == "authority_get_approval" and reqs.vocabulary["vendor_actions"] == ["get_workorder"]
    assert set(reqs.vocabulary["vendor_stated_values"]) >= {"SIGNED_OFF", "OPERATOR"}
    base = load_requirements(load_dogwood_inputs(T01).requirements, suite)
    assert base.vendor_only == () and base.vocabulary is None


def test_requirements_rejects_vendor_only_trace_that_the_contract_allows(tmp_path):
    inp = load_dogwood_inputs(T01)
    suite = temporal.load_suite(inp.traces_yaml)
    bad = tmp_path / "r.yaml"
    bad.write_text("base: t01_valid\nrequirements:\n  x: {requirement: 1, witnesses: [t02_rejected]}\nvendor_only_traces: [t01_valid]\n")
    with pytest.raises(ValueError, match="vendor_only_traces"):
        load_requirements(bad, suite)
