"""Sondera-style generator-critic (our reimplementation): deterministic critic, LLM judge, bounded regeneration."""

from pathlib import Path

import pytest

from pgi.generators.critic import SonderaConfig, deterministic_critique, judge_request, run
from pgi.generators.inputs import load_scenario_inputs
from pgi.generators.naive import NaiveConfig, build_request
from pgi.llm.cache import CachedLLM
from pgi.oracle import sym

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
S01 = DOMAIN / "scenarios" / "s01_close_after_approval"
WO = DOMAIN / "schema" / "wo.cedarschema"
REF = (S01 / "reference.cedar").read_text()
WEAK = (S01 / "weak_same_wo.cedar").read_text()


@pytest.fixture(autouse=True, scope="module")
def _symcc():
    try:
        sym.check_available()
    except sym.SymccUnavailable as e:
        pytest.skip(str(e))


class ScriptedProvider:
    """Answers generation and judge calls from two scripted queues; records every request."""

    name = "scripted"

    def __init__(self, generations, judgements):
        self.generations, self.judgements, self.seen = list(generations), list(judgements), []

    def call(self, model, messages, temperature, params):
        is_judge = "policy reviewer" in params["system"][0]["text"]
        self.seen.append(("judge" if is_judge else "gen", messages, params))
        text = (self.judgements if is_judge else self.generations).pop(0)
        return {"model": model, "content": [{"type": "text", "text": text}], "usage": {}}

    def text(self, raw):
        return raw["content"][0]["text"]

    def model_version(self, raw):
        return raw["model"]

    def usage(self, raw):
        return raw["usage"]


def write(tmp_path, text, name="p.cedar"):
    path = tmp_path / name
    path.write_text(text)
    return path


# ---- deterministic critic
def test_reference_passes_the_deterministic_critic(tmp_path):
    c = deterministic_critique(write(tmp_path, REF), WO)
    assert c.passed and c.validation.ok and not c.failures
    assert len(c.never_allowed) == 13  # 15 actions, reference grants 2


def test_invalid_policy_fails_without_running_symcc(tmp_path):
    c = deterministic_critique(write(tmp_path, "permit (principal, action, resource"), WO)
    assert not c.passed and not c.validation.ok and c.failures


def test_always_allow_fails(tmp_path):
    c = deterministic_critique(write(tmp_path, 'permit (principal, action == AOB::Action::"close_workorder", resource);'), WO)
    assert not c.passed and any("always allows" in f and "close_workorder" in f for f in c.failures)


def test_deny_everything_fails(tmp_path):
    c = deterministic_critique(write(tmp_path, "forbid (principal, action, resource);"), WO)
    assert not c.passed and any("denies every request for every action" in f for f in c.failures)


def test_runtime_error_fails(tmp_path):
    text = ('permit (principal, action == AOB::Action::"get_workorder_kpis", resource) when '
            '{ context.input has period_months && context.input.period_months + 9223372036854775807 > 0 };')
    c = deterministic_critique(write(tmp_path, text), WO)
    assert not c.passed and any("can raise a runtime error" in f for f in c.failures)


# ---- judge
def test_judge_sees_intent_and_policy_but_not_manifests_by_default():
    inp = load_scenario_inputs(S01)
    msgs, params = judge_request(inp, REF, SonderaConfig(model="m"))
    text = "".join(b["text"] for b in params["system"]) + msgs[0]["content"]
    assert inp.intent in text and REF in text
    assert "close_workorderArguments" not in text  # manifest JSON absent
    msgs2, params2 = judge_request(inp, REF, SonderaConfig(model="m", judge_sees_manifests=True))
    assert "close_workorderArguments" in "".join(b["text"] for b in params2["system"])


# ---- loop
def test_round_one_is_the_naive_request(tmp_path):
    inp = load_scenario_inputs(S01)
    provider = ScriptedProvider([REF], ["NO MISMATCHES"])
    run(CachedLLM(provider, tmp_path / "cache"), inp, SonderaConfig(model="m"), 0, tmp_path / "work")
    _, messages, params = provider.seen[0]
    assert (messages, params) == build_request(inp, NaiveConfig(model="m"))


def test_regenerates_on_failure_then_stops_when_both_critics_pass(tmp_path):
    provider = ScriptedProvider(["not cedar at all", REF], ["- wrong", "NO MISMATCHES"])
    res = run(CachedLLM(provider, tmp_path / "cache"), load_scenario_inputs(S01), SonderaConfig(model="m"), 0, tmp_path / "work")
    assert res.passed and res.rounds_used == 2 and res.final_policy == REF.strip()
    feedback = [m for kind, m, _ in provider.seen if kind == "gen"][1][0]["content"]
    assert "not cedar at all" in feedback and "- wrong" in feedback  # both critiques fed back
    assert feedback.endswith("Output only Cedar policies.")


def test_judge_rejection_alone_forces_a_new_round(tmp_path):
    provider = ScriptedProvider([WEAK, REF], ["- approval may be for a different work order", "NO MISMATCHES"])
    res = run(CachedLLM(provider, tmp_path / "cache"), load_scenario_inputs(S01), SonderaConfig(model="m"), 0, tmp_path / "work")
    assert res.rounds_used == 2 and res.rounds[0].deterministic.passed and not res.rounds[0].judge_passed


def test_gives_up_after_max_rounds_and_keeps_the_last_attempt(tmp_path):
    provider = ScriptedProvider(["bad 1", "bad 2", "bad 3"], ["- x", "- y", "- z"])
    res = run(CachedLLM(provider, tmp_path / "cache"), load_scenario_inputs(S01), SonderaConfig(model="m"), 0, tmp_path / "work")
    assert not res.passed and res.rounds_used == 3 and res.final_policy == "bad 3"
    assert sum(1 for kind, _, _ in provider.seen if kind == "gen") == 3
    assert sorted(p.name for p in (tmp_path / "work").glob("round*.cedar")) == ["round1.cedar", "round2.cedar", "round3.cedar"]
