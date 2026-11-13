"""Clean-run plumbing: replay reproduces records with zero API calls; blind spots and summaries are right."""

import dataclasses
import json
from pathlib import Path

import pytest

from pgi.generators import critic, naive
from pgi.generators.inputs import load_scenario_inputs
from pgi.llm.cache import CachedLLM
from pgi.oracle import sym
from pgi.runs.clean import run_naive, run_sondera, summarize, wilson
from pgi.runs.judge import score

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
S01 = DOMAIN / "scenarios" / "s01_close_after_approval"


@pytest.fixture(autouse=True, scope="module")
def _symcc():
    try:
        sym.check_available()
    except sym.SymccUnavailable as e:
        pytest.skip(str(e))


class Fake:
    """Generator returns the weak_same_wo policy; judge says NO MISMATCHES. Counts calls."""

    name = "fake"

    def __init__(self):
        self.calls = 0

    def call(self, model, messages, temperature, params):
        self.calls += 1
        judge = "policy reviewer" in params["system"][0]["text"]
        text = "NO MISMATCHES" if judge else "```cedar\n" + (S01 / "weak_same_wo.cedar").read_text() + "```"
        return {"model": f"{model}-v1", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
                "usage": {"input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 50}}

    def text(self, raw):
        return raw["content"][0]["text"]

    def model_version(self, raw):
        return raw["model"]

    def usage(self, raw):
        return raw["usage"]


def strip_hits(rows, run_dir):
    """Records minus what legitimately differs between a run and its replay: cache_hit and the run folder path."""
    s = json.dumps(rows, sort_keys=True, default=str).replace(str(run_dir), "RUN")
    return s.replace('"cache_hit": true', '"cache_hit": X').replace('"cache_hit": false', '"cache_hit": X')


def test_replay_makes_zero_api_calls_and_reproduces_records(tmp_path):
    inp = load_scenario_inputs(S01)
    cache = tmp_path / "cache"
    first = Fake()
    llm = CachedLLM(first, cache)
    rows1 = [run_naive(llm, inp, naive.NaiveConfig("claude-haiku-5-5"), i, tmp_path / "a" / f"n{i}") for i in range(2)]
    rows1 += [run_sondera(llm, inp, critic.SonderaConfig("claude-haiku-5-5"), i, tmp_path / "a" / f"s{i}") for i in range(2)]
    assert first.calls > 0
    replay_provider = Fake()
    replay = CachedLLM(replay_provider, cache, allow_api=False)
    rows2 = [run_naive(replay, inp, naive.NaiveConfig("claude-haiku-5-5"), i, tmp_path / "b" / f"n{i}") for i in range(2)]
    rows2 += [run_sondera(replay, inp, critic.SonderaConfig("claude-haiku-5-5"), i, tmp_path / "b" / f"s{i}") for i in range(2)]
    assert replay_provider.calls == 0 and replay.api_calls == 0
    assert strip_hits(rows1, tmp_path / "a") == strip_hits(rows2, tmp_path / "b")
    assert (tmp_path / "a/n0/policy.cedar").read_text() == (tmp_path / "b/n0/policy.cedar").read_text()


def test_blind_spot_is_flagged_when_the_universe_lacks_the_witness(tmp_path):
    """weak_same_wo over a universe without c3: enumeration sees no surplus, symcc does -> blind spot on close."""
    lines = (S01 / "universe.yaml").read_text().splitlines()
    i = next(k for k, l in enumerate(lines) if l.strip().startswith("- id: c3"))
    j = next(k for k in range(i + 1, len(lines)) if lines[k].strip().startswith("- id:"))
    shrunk = tmp_path / "universe.yaml"
    shrunk.write_text("\n".join(lines[:i] + lines[j:]) + "\n")
    inp = load_scenario_inputs(S01)
    inp = dataclasses.replace(inp, folder=tmp_path)
    (tmp_path / "reference.cedar").write_text((S01 / "reference.cedar").read_text())
    r = score(S01 / "weak_same_wo.cedar", inp)
    assert r["enumeration"]["surplus"] == []
    assert r["symbolic"]["blind_spots"] == ['AOB::Action::"close_workorder"']
    assert r["symbolic"]["replay_failures"] == []


def test_invalid_policy_gets_no_oracle_result(tmp_path):
    p = tmp_path / "bad.cedar"
    p.write_text("I can't help with that.")
    r = score(p, load_scenario_inputs(S01))
    assert r == {"validation": r["validation"], "valid": False}


def test_wilson_interval():
    assert wilson(0, 0) is None
    lo, hi = wilson(10, 20)
    assert lo < 0.5 < hi and abs((lo + hi) / 2 - 0.5) < 1e-9
    assert wilson(20, 20)[1] == 1.0 and wilson(0, 20)[0] == 0.0


def test_summary_counts(tmp_path):
    inp = load_scenario_inputs(S01)
    llm = CachedLLM(Fake(), tmp_path / "cache")
    rows = [run_naive(llm, inp, naive.NaiveConfig("claude-haiku-5-5"), i, tmp_path / f"n{i}") for i in range(2)]
    s = summarize("claude-haiku-5-5", rows)
    assert s["n"] == 2 and s["valid"] == 2 and s["nonempty_surplus"] == 2 and s["nonempty_deficit"] == 0
    assert s["surplus_case_counts"] == {"c3": 2}
    assert s["clean_envelope"] == ["c2", "c3", "list_main"]
    assert s["model_versions"] == ["claude-haiku-5-5-v1"] and s["blind_spots"] == []


# ---- 2a: judge pass rates and judge flips on unchanged behaviour
from pgi.runs.judge import same_behaviour  # noqa: E402

REF_TEXT = (S01 / "reference.cedar").read_text()
WEAK_TEXT = (S01 / "weak_same_wo.cedar").read_text()


class Scripted(Fake):
    """Generations and judge replies from two queues (Fake's record format)."""

    def __init__(self, generations, judgements):
        super().__init__()
        self.generations, self.judgements = list(generations), list(judgements)

    def call(self, model, messages, temperature, params):
        self.calls += 1
        judge = "policy reviewer" in params["system"][0]["text"]
        text = self.judgements.pop(0) if judge else "```cedar\n" + self.generations.pop(0) + "```"
        return {"model": model, "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}


def write(tmp_path, name, text):
    (tmp_path / name).write_text(text)
    return tmp_path / name


def test_same_behaviour(tmp_path):
    inp = load_scenario_inputs(S01)
    ref = write(tmp_path, "a.cedar", REF_TEXT)
    commented = write(tmp_path, "b.cedar", "// only a comment differs\n" + REF_TEXT)
    weak = write(tmp_path, "c.cedar", WEAK_TEXT)
    bad = write(tmp_path, "d.cedar", "not cedar")
    assert same_behaviour(ref, commented, inp) is True
    assert same_behaviour(ref, weak, inp) is False
    assert same_behaviour(ref, bad, inp) is None  # an invalid round cannot be compared


def test_judge_flip_on_identical_behaviour_is_recorded(tmp_path):
    """Round 2 = round 1 plus a comment; the judge rejects then passes: one flip on unchanged behaviour."""
    prov = Scripted([REF_TEXT, "// note\n" + REF_TEXT], ["- something", "NO MISMATCHES"])
    row = run_sondera(CachedLLM(prov, tmp_path / "cache"), load_scenario_inputs(S01),
                      critic.SonderaConfig("claude-haiku-5-5"), 0, tmp_path / "s0")
    (pair,) = row["critic"]["round_pairs"]
    assert pair == {"rounds": [1, 2], "valid": [True, True], "same_text": False, "same_behaviour": True,
                    "judge": [False, True], "judge_changed": True}


def test_no_pair_when_judge_and_critic_pass_in_round_one(tmp_path):
    prov = Scripted([REF_TEXT], ["NO MISMATCHES"])
    row = run_sondera(CachedLLM(prov, tmp_path / "cache"), load_scenario_inputs(S01),
                      critic.SonderaConfig("claude-haiku-5-5"), 0, tmp_path / "s0")
    assert row["critic"]["round_pairs"] == [] and row["critic"]["passed"] and row["critic"]["rounds_used"] == 1


def _critic_row(passed, rounds_used, pairs=()):
    return {"sample": 0, "calls": [], "oracle": {"valid": False},
            "critic": {"passed": passed, "rounds_used": rounds_used, "round_pairs": list(pairs)}}


def _pair(same, changed):
    return {"rounds": [1, 2], "valid": [True, True], "same_text": False, "same_behaviour": same,
            "judge": [False, changed], "judge_changed": changed}


def test_summary_judge_pass_rates_and_noise_floor():
    rows = [_critic_row(True, 1),
            _critic_row(True, 2, [_pair(True, True)]),
            _critic_row(False, 3, [_pair(True, False), _pair(False, False)]),
            _critic_row(True, 3, [_pair(None, False), _pair(False, True)])]
    s = summarize("claude-haiku-5-5", rows)
    assert s["critic_passed"] == 3 and s["critic_pass_share"] == 0.75 and s["critic_pass_ci95"] == wilson(3, 4)
    assert s["critic_passed_round1"] == 1 and s["critic_passed_round1_share"] == 0.25
    assert s["rounds_to_pass_counts"] == {1: 1, 2: 1, 3: 1}       # passed samples only
    assert s["rounds_used_counts"] == {1: 1, 2: 1, 3: 2}          # unchanged: every sample
    # denominator: consecutive pairs with identical behaviour (same=None and same=False excluded)
    assert s["judge_flips_on_same_behaviour"] == {"flips": 1, "pairs": 2}


# ---- 2b: per-request allow counts
def _valid_row(allow):
    return {"sample": 0, "calls": [], "oracle": {"valid": True, "enumeration": {"allow_set": allow, "surplus": [], "deficit": []},
                                                 "symbolic": {"implies_reference": True, "per_action": [], "blind_spots": [], "replay_failures": []}}}


def test_summary_per_request_allow_counts():
    rows = [_valid_row(["a", "b"]), _valid_row(["a"]), _valid_row([]), {"sample": 3, "calls": [], "oracle": {"valid": False}}]
    s = summarize("claude-haiku-5-5", rows, case_ids=["a", "b", "c"], reference_allow=["a"])
    assert s["allow_counts"] == {"a": {"k": 2, "n": 3, "ci95": wilson(2, 3)},
                                 "b": {"k": 1, "n": 3, "ci95": wilson(1, 3)},
                                 "c": {"k": 0, "n": 3, "ci95": wilson(0, 3)}}   # n = valid samples
    assert s["reference_allow_set"] == ["a"]
    assert s["clean_envelope"] == ["a", "b"]  # union envelope unchanged


def test_markdown_has_one_case_table_per_scenario():
    from pgi.runs.clean import markdown
    rows = [_valid_row(["a"])]
    summ = {"s01/naive": summarize("claude-haiku-5-5", rows, case_ids=["a", "b"], reference_allow=["a"]),
            "s01/sondera": summarize("claude-haiku-5-5", rows, case_ids=["a", "b"], reference_allow=["a"])}
    md = markdown({"run_id": "r", "model": "m", "n": 1}, summ)
    assert "### s01: allow counts per request" in md
    assert "| case | P_ref | naive | sondera |" in md
    assert "| a | ✓ | 1/1 | 1/1 |" in md and "| b |  | 0/1 | 0/1 |" in md


# ---- 2c: literal provenance per sample and per scenario x generator
def test_each_sample_records_literal_provenance(tmp_path):
    """Fake returns weak_same_wo. Its APPR literal is stated by the trusted enum and by approve_workorder's free text."""
    inp = load_scenario_inputs(S01)
    row = run_naive(CachedLLM(Fake(), tmp_path / "cache"), inp, naive.NaiveConfig("claude-haiku-5-5"), 0, tmp_path / "n0")
    prov = {r["literal"]: r for r in row["provenance"]}
    assert json.loads((tmp_path / "n0" / "provenance.json").read_text()) == row["provenance"]
    appr = prov['PGI::ApprovalStatus::"APPR"']["sources"]
    assert "trusted_schema" in appr and "generated_schema" not in appr
    assert any("approve_workorder" in loc for loc in appr["manifest_free_text"])
    assert "intent" in prov['"MAIN"']["sources"]


def test_unparseable_policy_gets_a_provenance_error_not_a_crash(tmp_path):
    class Junk(Fake):
        def call(self, model, messages, temperature, params):
            return {**super().call(model, messages, temperature, params),
                    "content": [{"type": "text", "text": "I can't help with that."}]}
    row = run_naive(CachedLLM(Junk(), tmp_path / "cache"), load_scenario_inputs(S01),
                    naive.NaiveConfig("claude-haiku-5-5"), 0, tmp_path / "n0")
    assert "does not parse" in row["provenance"]["error"]


def test_summary_literal_provenance_counts_samples_not_occurrences():
    lit = lambda text, n, src: {"literal": text, "kind": "string", "occurrences": n, "sources": src}
    rows = [_valid_row([]) | {"provenance": [lit('"MAIN"', 3, {"intent": ["intent.md"]}), lit('"X"', 1, {})]},
            _valid_row([]) | {"provenance": [lit('"MAIN"', 1, {"intent": ["intent.md"]})]},
            {"sample": 2, "calls": [], "oracle": {"valid": False}, "provenance": {"error": "does not parse"}}]
    s = summarize("claude-haiku-5-5", rows)
    assert s["literal_provenance"] == {
        '"MAIN"': {"kind": "string", "samples": 2, "sources": {"intent": ["intent.md"]}},
        '"X"': {"kind": "string", "samples": 1, "sources": {}}}
    assert s["provenance_parsed"] == 2


def test_markdown_has_one_literal_table_per_scenario():
    from pgi.runs.clean import markdown
    lit = {"literal": '"MAIN"', "kind": "string", "occurrences": 1, "sources": {"intent": ["intent.md"], "manifest_other": ["x"]}}
    rows = [_valid_row([]) | {"provenance": [lit]}]
    summ = {"s01/naive": summarize("m", rows), "s01/sondera": summarize("m", rows + rows)}
    md = markdown({"run_id": "r", "model": "m", "n": 1}, summ)
    assert "### s01: literal provenance" in md
    assert '| `"MAIN"` | 1/1 | 2/2 | intent, manifest_other |' in md
