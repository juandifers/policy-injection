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
