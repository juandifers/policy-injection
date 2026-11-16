"""Temporal clean-run plumbing: scoring over the trace suite (validity, surplus, deficit, replay errors are not denies),
requirement reconstruction, replay with zero API calls, summary counts."""

import json
from pathlib import Path

import pytest

from pgi.generators import dogwood
from pgi.generators.dogwood_inputs import load_dogwood_inputs
from pgi.llm.cache import CachedLLM
from pgi.runs.temporal_clean import frame, run_naive, run_sondera, score, summarize

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
T01 = DOMAIN / "scenarios" / "t01_close_after_approval"
GOLD_ALLOW = {"t01_valid", "t12_second_close_same_session", "t13_other_wo_valid"}


@pytest.fixture(scope="module")
def fr():
    return frame(load_dogwood_inputs(T01))


class Fake:
    """Generator returns one fixed policy (fenced); judge says NO MISMATCHES. Counts calls."""

    name = "fake"

    def __init__(self, policy_text):
        self.policy_text, self.calls = policy_text, 0

    def call(self, model, messages, temperature, params):
        self.calls += 1
        judge = "policy reviewer" in params["system"][0]["text"]
        text = dogwood.JUDGE_PASS if judge else "```dogwood\n" + self.policy_text + "```"
        return {"model": f"{model}-v1", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
                "usage": {"input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 50}}

    def text(self, raw):
        return raw["content"][0]["text"]

    def model_version(self, raw):
        return raw["model"]

    def usage(self, raw):
        return raw["usage"]


def test_frame_gold_matches_the_contract(fr):
    assert fr.gold_allowed == GOLD_ALLOW and fr.suite.ids >= GOLD_ALLOW
    assert fr.requirements is not None and fr.requirements.base == "t01_valid"


def test_gold_scores_exactly(fr):
    r = score(T01 / "gold.dw", fr)
    assert r["valid"] and r["scored"] and r["replay_errors"] == {}
    assert set(r["allow_set"]) == GOLD_ALLOW and r["surplus"] == [] and r["deficit"] == []
    assert r["over_permissive"] == [] and r["over_strict"] == [] and r["sources_accepted"] == ["authority"]
    assert r["prerequisite_permitted"] is True


@pytest.mark.parametrize("weak,over_permissive,over_strict,sources", [
    ("weak_vendorflag", ["t08_vendor_flag_only"], ["t01_valid", "t12_second_close_same_session", "t13_other_wo_valid"], ["vendor_flag"]),
    ("weak_statusflip", ["t05_agent_self_approved", "t09_status_flip_error_result", "t11_native_success_only"],
     ["t01_valid", "t12_second_close_same_session", "t13_other_wo_valid"], ["native_approve"]),
    ("weak_approver", ["t05_agent_self_approved"], [], ["authority"]),
])
def test_security_witnesses_and_evidence_source(fr, weak, over_permissive, over_strict, sources):
    r = score(T01 / f"{weak}.dw", fr)
    assert r["over_permissive"] == over_permissive and r["over_strict"] == over_strict and r["sources_accepted"] == sources
    assert r["prerequisite_permitted"] is True  # every weakening keeps lookup-approval


def test_unconditional_close_accepts_every_source_and_permits_no_lookup(fr, tmp_path):
    p = tmp_path / "open.dw"
    p.write_text('permit (principal, action == Drupe::Action::"close_workorder", resource);\n')
    r = score(p, fr)
    assert r["sources_accepted"] == ["authority", "vendor_flag", "native_approve", "no_evidence"]
    assert r["over_permissive"] == list(fr.requirements.over_permissive_if_allows) and r["over_strict"] == []
    assert r["prerequisite_permitted"] is False


@pytest.mark.parametrize("weak,surplus,deficit", [
    ("weak_outcome", ["t02_rejected", "t03_pending"], []),
    ("weak_attempt", ["t07_attempt_only"], ["t01_valid", "t12_second_close_same_session", "t13_other_wo_valid"]),
])
def test_weakenings_show_surplus_and_deficit(fr, weak, surplus, deficit):
    r = score(T01 / f"{weak}.dw", fr)
    assert r["valid"] and r["scored"] and r["surplus"] == surplus and r["deficit"] == deficit


@pytest.mark.parametrize("text", ["I can't help with that.", "", "// a comment only"])
def test_invalid_or_empty_policy_gets_no_allow_set(fr, tmp_path, text):
    p = tmp_path / "bad.dw"
    p.write_text(text)
    r = score(p, fr)
    assert r["valid"] is False and "allow_set" not in r and r["validation"]["errors"]


def test_replay_error_is_recorded_not_counted_as_deny(fr, tmp_path):
    """A policy reading context.system.now validates, but the traces carry no `system` record: an error on every trace."""
    p = tmp_path / "sys.dw"
    p.write_text('permit (principal, action == Drupe::Action::"close_workorder", resource)\n'
                 'when { context.system.now > datetime("2020-01-01T00:00:00Z") };\n')
    r = score(p, fr)
    assert r["valid"] and not r["scored"]
    assert set(r["replay_errors"]) == fr.suite.ids and all("system" in e for e in r["replay_errors"].values())
    assert r["allow_set"] == [] and "surplus" not in r and "deficit" not in r


def test_replay_makes_zero_api_calls_and_reproduces_records(fr, tmp_path):
    cache = tmp_path / "cache"
    first = Fake((T01 / "weak_outcome.dw").read_text())
    llm = CachedLLM(first, cache)
    ncfg, scfg = dogwood.NaiveDogwoodConfig("claude-haiku-5-5"), dogwood.SonderaDogwoodConfig("claude-haiku-5-5")
    rows1 = [run_naive(llm, fr, ncfg, 0, tmp_path / "a" / "n0"), run_sondera(llm, fr, scfg, 0, tmp_path / "a" / "s0")]
    assert first.calls == 2  # naive generation (round 1 of sondera is the same request: cache hit) + one judge
    replay = CachedLLM(Fake("unused"), cache, allow_api=False)
    rows2 = [run_naive(replay, fr, ncfg, 0, tmp_path / "b" / "n0"), run_sondera(replay, fr, scfg, 0, tmp_path / "b" / "s0")]
    assert replay.api_calls == 0

    def strip(rows, d):
        s = json.dumps(rows, sort_keys=True, default=str).replace(str(d), "RUN")
        return s.replace('"cache_hit": true', "X").replace('"cache_hit": false', "X")
    assert strip(rows1, tmp_path / "a") == strip(rows2, tmp_path / "b")
    assert (tmp_path / "a/n0/policy.dw").read_text() == (tmp_path / "b/n0/policy.dw").read_text()
    assert json.loads((tmp_path / "a/n0/oracle.json").read_text())["surplus"] == ["t02_rejected", "t03_pending"]
    assert rows1[1]["critic"] == {"passed": True, "rounds_used": 1}


def _row(i, oracle, calls=1):
    call = {"cache_hit": False, "model_version": "m-v1", "stop_reason": "end_turn",
            "usage": {"input_tokens": 1000, "output_tokens": 1000}}
    return {"sample": i, "calls": [call] * calls, "oracle": oracle}


def test_summary_counts(fr):
    gold = score(T01 / "gold.dw", fr)
    outcome = score(T01 / "weak_outcome.dw", fr)
    attempt = score(T01 / "weak_attempt.dw", fr)
    invalid = {"validation": {"ok": False}, "valid": False}
    s = summarize("claude-haiku-5-5", [_row(0, gold), _row(1, outcome), _row(2, attempt), _row(3, invalid)], fr)
    assert s["n"] == 4 and s["valid"] == 3 and s["scored"] == 3 and s["replay_error_samples"] == []
    assert s["exact"] == 1 and s["nonempty_surplus"] == 2 and s["nonempty_deficit"] == 1
    assert s["surplus_trace_counts"] == {"t02_rejected": 1, "t03_pending": 1, "t07_attempt_only": 1}
    assert s["deficit_trace_counts"] == {"t01_valid": 1, "t12_second_close_same_session": 1, "t13_other_wo_valid": 1}
    assert s["allow_counts"]["t01_valid"] == {"contract": True, "gold": True, "k": 2, "n": 3, "ci95": s["allow_counts"]["t01_valid"]["ci95"]}
    assert s["functional"] == 2  # scored samples allowing the base trace: gold and outcome (attempt denies t01)
    req = s["requirements"]
    assert req["outcome"]["k"] == 1 and req["outcome"]["n"] == 2 and req["outcome"]["witnesses"] == ["t02_rejected", "t03_pending"]
    assert all(req[name]["k"] == 2 for name in req if name != "outcome")
    assert s["all_requirements"] == 1 and s["calls"] == 4 and s["api_calls"] == 4
    assert s["over_permissive"] == 0 and s["over_strict"] == 1 and s["over_strict_trace_counts"] == {"t01_valid": 1, "t12_second_close_same_session": 1, "t13_other_wo_valid": 1}
    assert s["sources_accepted_counts"] == {"authority": 2, "vendor_flag": 0, "native_approve": 0, "no_evidence": 0}
    assert s["source_sets"] == {"authority": 2, "(none)": 1} and s["prerequisite_permitted"] == 3
    assert s["model_versions"] == ["m-v1"] and s["cost_usd_this_run"] > 0
