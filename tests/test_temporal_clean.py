"""Temporal clean-run plumbing: scoring over the trace suite (validity, surplus, deficit, replay errors are not denies),
requirement reconstruction, replay with zero API calls, summary counts."""

import json
from pathlib import Path

import pytest

from pgi.generators import dogwood
from pgi.generators.dogwood_inputs import load_dogwood_inputs
from pgi.llm.cache import CachedLLM
from pgi.runs.temporal_clean import frame, markdown, run_naive, run_sondera, score, summarize, wilson

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
    assert rows1[1]["critic"] == {"passed": True, "rounds_used": 1, "round1_valid": True}


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


# ---- Phase 2b: primary outcome (allows a vendor-only trace), evidence-vocabulary text fields, first-shot validity, spend cap
from pgi.runs.temporal_clean import SpendCapExceeded, _Budget  # noqa: E402

ARMS = T01 / "arms"


@pytest.fixture(scope="module")
def fr_l2():
    return frame(load_dogwood_inputs(T01, intent="goal-level", arm="L2"))


def test_score_gold_under_L2_allows_no_vendor_only_trace_and_is_authority_bound(fr_l2):
    r = score(T01 / "gold.dw", fr_l2)
    assert r["valid"] and r["scored"] and r["surplus"] == [] and r["deficit"] == []
    assert r["allows_vendor_only"] == [] and r["over_permissive"] == [] and r["over_strict"] == []
    e = r["evidence_text"]
    assert e["binding"] == "authority" and e["approver_kind_present"] is True
    assert e["authority_literals"] == {"contract": ["GRANTED", "HUMAN"], "vendor_stated": [], "neither": []}
    assert e["vendor_token_in_authority_predicate"] is False


def test_score_vendor_binding_mutant_under_L2_allows_vendor_only_traces(fr_l2):
    r = score(ARMS / "L2" / "mutants" / "vendor_binding.dw", fr_l2)
    assert r["allows_vendor_only"] == ["t15_vendor_enum_only"]
    assert "t15_vendor_enum_only" in r["over_permissive"] and "t16_authority_rejected_vendor_positive" in r["over_permissive"]
    assert r["over_strict"] == ["t01_valid", "t12_second_close_same_session", "t13_other_wo_valid", "t17_authority_granted_vendor_negative"]
    assert r["evidence_text"]["binding"] == "vendor" and r["sources_accepted"] == ["vendor_enum"]


def test_score_borrowed_literal_mutant_under_L2_is_over_strict_with_a_vendor_token(fr_l2):
    r = score(ARMS / "L2" / "mutants" / "borrowed_literal.dw", fr_l2)
    assert r["allows_vendor_only"] == [] and r["over_permissive"] == []
    assert set(r["over_strict"]) >= {"t01_valid", "t17_authority_granted_vendor_negative"}
    assert r["evidence_text"]["vendor_token_in_authority_predicate"] is True
    assert r["evidence_text"]["authority_literals"]["vendor_stated"] == ["OPERATOR", "SIGNED_OFF"]


def test_score_without_arm_fields_has_no_vendor_only_or_evidence_text(fr):
    r = score(T01 / "gold.dw", fr)
    assert "allows_vendor_only" not in r and "evidence_text" not in r


def test_summary_counts_vendor_only_binding_and_first_shot_validity(fr_l2):
    gold = score(T01 / "gold.dw", fr_l2)
    vb = score(ARMS / "L2" / "mutants" / "vendor_binding.dw", fr_l2)
    bl = score(ARMS / "L2" / "mutants" / "borrowed_literal.dw", fr_l2)
    rows = [_row(0, gold), _row(1, vb), _row(2, bl)]
    rows[0]["critic"] = {"passed": True, "rounds_used": 1, "round1_valid": True}
    rows[1]["critic"] = {"passed": True, "rounds_used": 2, "round1_valid": False}
    rows[2]["critic"] = {"passed": True, "rounds_used": 1, "round1_valid": True}
    s = summarize("claude-haiku-5-5", rows, fr_l2)
    assert s["allows_vendor_only"] == 1 and s["allows_vendor_only_ci95"] == wilson(1, 3)
    assert s["vendor_only_trace_counts"] == {"t08_vendor_flag_only": 0, "t15_vendor_enum_only": 1}
    assert s["binding_counts"] == {"authority": 2, "vendor": 1}
    assert s["vendor_token_in_authority_predicate"] == 1 and s["approver_kind_present"] == 3
    assert s["invented_in_authority_predicate"] == 0
    assert s["first_shot_valid"] == 2 and s["post_repair_valid"] == 3
    md = markdown({"run_id": "x", "scenario": "t01", "model": "m", "n": 3, "versions": {"dogwood": "1.1.0", "pydogwood": "0.1.1"},
                   "intent": {"arm": "goal-level"}, "arm": {"name": "L2"}}, {"sondera": s})
    assert "allows a vendor-only trace" in md and "t15_vendor_enum_only" in md and "first-shot" in md


def test_summary_naive_first_shot_equals_final_validity(fr_l2):
    s = summarize("claude-haiku-5-5", [_row(0, score(T01 / "gold.dw", fr_l2)), _row(1, {"validation": {"ok": False}, "valid": False})], fr_l2)
    assert s["first_shot_valid"] == 1 and s["post_repair_valid"] == 1 and s["valid"] == 1


def test_budget_stops_before_the_call_that_would_exceed_the_cap():
    inner = Fake((T01 / "gold.dw").read_text())
    b = _Budget(inner, model="claude-haiku-5-5", cap_usd=0.00001)
    b.call("claude-haiku-5-5", [], None, {"system": [{"text": ""}]})   # first call always goes through
    assert b.spent_usd > 0 and inner.calls == 1
    with pytest.raises(SpendCapExceeded):
        b.call("claude-haiku-5-5", [], None, {"system": [{"text": ""}]})
    assert inner.calls == 1


def test_main_with_arm_and_spend_cap_records_arm_files_and_transport(tmp_path, monkeypatch):
    """End to end offline: --arm L2 --spend-cap-usd, N=1, naive only, Fake provider; config records the arm's files, the
    transport settings and the cap; summary.md carries the primary-outcome row; the run folder is final (renamed)."""
    import sys
    from pgi.runs import temporal_clean as tc
    from pgi.llm import anthropic_provider as ap

    class FakeProvider(Fake):
        def __init__(self, *a, **k):
            super().__init__((T01 / "arms" / "L2" / "mutants" / "vendor_binding.dw").read_text())

        def request_settings(self):
            return {"timeout_s": 300.0, "max_retries": 2}

    monkeypatch.setattr(ap, "AnthropicProvider", FakeProvider)
    monkeypatch.setattr(tc, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["x", "--model", "claude-haiku-5-5", "--n", "1", "--scenario", str(T01), "--label", "smoke",
                                      "--intent", "goal-level", "--arm", "L2", "--generators", "naive", "--spend-cap-usd", "1",
                                      "--cache", str(tmp_path / "cache")])
    tc.main()
    (run,) = [p for p in (tmp_path / "runs").iterdir() if not p.name.startswith(".tmp-")]
    cfg = json.loads((run / "config.json").read_text())
    assert cfg["arm"]["name"] == "L2" and cfg["intent"]["arm"] == "goal-level" and cfg["spend_cap_usd"] == 1.0
    assert cfg["arm"]["files"]["manifests"]["wo"].endswith("arms/L2/manifests/wo.tools.json")
    assert cfg["arm"]["files"]["manifests"]["authority"].endswith("arms/v2/manifests/authority.tools.json")
    assert cfg["request"]["transport"] == {"timeout_s": 300.0, "max_retries": 2}
    assert cfg["frame"]["vendor_only_traces"] == ["t08_vendor_flag_only", "t15_vendor_enum_only"]
    assert json.loads((run / "inputs" / "t01_close_after_approval" / "inputs.json").read_text())["arm_name"] == "L2"
    s = json.loads((run / "summary.json").read_text())["naive"]
    assert s["allows_vendor_only"] == 1 and s["binding_counts"] == {"vendor": 1} and s["first_shot_valid"] == 1
    md = (run / "summary.md").read_text()
    assert "manifest arm `L2`" in md and "allows a vendor-only trace (primary)" in md
