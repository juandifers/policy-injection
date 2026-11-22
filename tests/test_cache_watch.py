"""Prompt-cache telemetry, the circuit breaker and the run-level prefix rule (Phase 3, 2026-11-20), plus `--plan`.

Everything reads the API's usage fields (cache_creation_input_tokens, cache_read_input_tokens, input_tokens, output_tokens)
through the provider interface (`cache_usage`); a provider that reports none disables telemetry and the breaker with a
logged reason. Breaker: once a prefix has been written in this process, three consecutive fresh calls on it with zero cache
reads abort the run; only a read resets the counter (a re-write with zero reads is a miss). Run-level rule (split layout):
every fresh call's prefix hash must be one the run registered up front, checked before the call is sent. Calls are
sequential: a second call on a prefix whose first call is still in flight is refused.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pgi.generators import dogwood
from pgi.generators.dogwood import NaiveDogwoodConfig, SonderaDogwoodConfig, build_request, judge_request
from pgi.generators.dogwood_inputs import load_dogwood_inputs
from pgi.llm.anthropic_provider import AnthropicProvider
from pgi.llm.cache import CachedLLM
from pgi.llm.prefix import prefix_hash
from pgi.llm.pricing import PRICES, cost
from pgi.runs.cache_watch import (CALIBRATION, recorded_output_mean, CacheBreakerTripped, ConcurrentPrefixCall, PrefixChanged, PrefixWatch, cost_split,
                                  estimate_tokens, plan, plan_text, recorded_prefix)
from pgi.runs.clean import _call_record
from pgi.runs.temporal_clean import SpendCapExceeded, _Budget

ROOT = Path(__file__).resolve().parents[1]
T01 = ROOT / "domains" / "assetopsbench" / "scenarios" / "t01_close_after_approval"
MODEL = "claude-sonnet-5-5"
SYSTEM = [{"type": "text", "text": "static one"}, {"type": "text", "text": "static two", "cache_control": {"type": "ephemeral"}}]
PARAMS = {"system": SYSTEM, "max_tokens": 10, "thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}
PARAMS_B = {**PARAMS, "system": [{"type": "text", "text": "other", "cache_control": {"type": "ephemeral"}}]}
H, H_B = prefix_hash(MODEL, PARAMS), prefix_hash(MODEL, PARAMS_B)


def usage(write=0, read=0, inp=300, out=1000) -> dict:
    return {"cache_creation_input_tokens": write, "cache_read_input_tokens": read, "input_tokens": inp, "output_tokens": out}


class Scripted:
    """Returns the next scripted usage per call; records calls. `reports` False = a provider without cache fields."""

    name = "scripted"

    def __init__(self, usages, reports=True):
        self.usages, self.calls, self.reports = list(usages), 0, reports

    def call(self, model, messages, temperature, params):
        self.calls += 1
        u = self.usages.pop(0)
        return {"model": model, "content": [{"type": "text", "text": "permit (principal, action, resource);"}], "usage": u}

    def text(self, raw):
        return raw["content"][0]["text"]

    def model_version(self, raw):
        return raw["model"]

    def usage(self, raw):
        return raw["usage"]

    def request_settings(self):
        return {"timeout_s": 0, "max_retries": 0}

    def cache_usage(self, raw):
        if not self.reports:
            return None
        u = raw["usage"]
        return {k: u.get(k, 0) for k in ("cache_creation_input_tokens", "cache_read_input_tokens", "input_tokens", "output_tokens")}


class NoCacheFields(Scripted):
    """A provider that does not implement cache_usage at all."""

    cache_usage = None


# ---- cost split
def test_cost_split_matches_pricing():
    u = usage(write=35000, read=0, inp=700, out=1500)
    s = cost_split(MODEL, u)
    p = PRICES[MODEL]
    assert s["tokens"] == {"cache_write": 35000, "cache_read": 0, "uncached_input": 700, "output": 1500}
    assert s["usd"]["cache_write"] == pytest.approx(35000 * p["cache_write_5m"] / 1e6)
    assert s["usd"]["output"] == pytest.approx(1500 * p["output"] / 1e6)
    assert s["total_usd"] == pytest.approx(cost(MODEL, u))
    assert cost_split(MODEL, {})["total_usd"] == 0.0


# ---- the watch
def test_write_then_reads_then_three_misses_trip(caplog):
    w = PrefixWatch()
    w.before(H)
    assert w.after(H, usage(write=100))["miss"] is False
    for _ in range(3):
        w.before(H)
        assert w.after(H, usage(read=100))["miss"] is False
    with caplog.at_level(logging.WARNING):
        w.before(H)
        r1 = w.after(H, usage(write=100))      # re-write with zero reads: a miss (change 2)
        w.before(H)
        r2 = w.after(H, usage())
    assert (r1["miss"], r1["consecutive_misses"]) == (True, 1) and (r2["miss"], r2["consecutive_misses"]) == (True, 2)
    assert sum("cache miss" in m for m in caplog.messages) == 2
    w.before(H)
    with pytest.raises(CacheBreakerTripped, match="3 consecutive"):
        w.after(H, usage(write=100))
    s = w.summary()["prefixes"][H]
    assert (s["calls"], s["writes"], s["reads"], s["misses"], s["max_consecutive_misses"]) == (7, 3, 3, 3, 3)


def test_only_a_read_resets_the_counter():
    w = PrefixWatch()
    w.before(H)
    w.after(H, usage(write=100))
    for _ in range(2):
        w.before(H)
        w.after(H, usage())
    w.before(H)
    w.after(H, usage(read=100))          # reset
    for _ in range(2):
        w.before(H)
        w.after(H, usage())              # 2 misses again, no trip
    assert w.summary()["prefixes"][H]["max_consecutive_misses"] == 2


def test_a_prefix_never_written_never_trips_but_is_logged(caplog):
    w = PrefixWatch()
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            w.before(H)
            w.after(H, usage())
    assert all("never written" in m or "no cache write" in m for m in caplog.messages) and caplog.messages
    assert w.summary()["prefixes"][H]["written"] is False


def test_prefixes_are_tracked_independently():
    w = PrefixWatch()
    for h in (H, H_B):
        w.before(h)
        w.after(h, usage(write=10))
    for _ in range(2):
        w.before(H)
        w.after(H, usage())
    w.before(H_B)
    assert w.after(H_B, usage(read=10))["consecutive_misses"] == 0
    assert w.summary()["prefixes"][H]["max_consecutive_misses"] == 2


def test_run_level_rule_rejects_an_unregistered_prefix_before_the_call():
    w = PrefixWatch(expected={"generation": H})
    w.before(H)
    w.after(H, usage(write=10))
    with pytest.raises(PrefixChanged, match="generation"):
        w.before(H_B)
    assert H_B not in w.summary()["prefixes"] and not w.in_flight


def test_in_flight_guard_enforces_sequential_calls():
    w = PrefixWatch()
    w.before(H)
    with pytest.raises(ConcurrentPrefixCall):
        w.before(H)
    w.after(H, usage(write=10))
    w.before(H)      # fine again


def test_disabled_watch_records_the_reason_and_never_trips(caplog):
    w = PrefixWatch()
    with caplog.at_level(logging.WARNING):
        w.before(H)
        r = w.after(H, None)
    assert r["telemetry"] == "disabled" and w.enabled is False and "reports no cache usage" in w.disabled_reason
    for _ in range(5):
        w.before(H)
        w.after(H, None)
    assert w.summary()["enabled"] is False and w.summary()["disabled_reason"]


def test_summary_hit_rate_and_cost_split():
    w = PrefixWatch(model=MODEL)
    w.before(H)
    w.after(H, usage(write=1000, out=10))
    for _ in range(3):
        w.before(H)
        w.after(H, usage(read=1000, out=10))
    s = w.summary()
    assert s["hit_rate"] == {"k": 3, "n": 4}
    assert s["cost_split"]["tokens"] == {"cache_write": 1000, "cache_read": 3000, "uncached_input": 1200, "output": 40}
    assert s["cost_split"]["total_usd"] == pytest.approx(sum(cost(MODEL, u) for u in [usage(write=1000, out=10)] + [usage(read=1000, out=10)] * 3))


# ---- the budget wrapper carries the watch
def test_budget_trips_the_breaker_and_stops_before_the_fourth_miss():
    p = Scripted([usage(write=100), usage(), usage(), usage(), usage()])
    b = _Budget(p, MODEL, cap_usd=None, watch=PrefixWatch())
    for _ in range(3):
        b.call(MODEL, [], None, PARAMS)
    with pytest.raises(CacheBreakerTripped):
        b.call(MODEL, [], None, PARAMS)
    assert p.calls == 4 and len(p.usages) == 1
    assert b.watch.summary()["prefixes"][H]["misses"] == 3


def test_budget_checks_the_registered_prefix_before_sending():
    p = Scripted([usage(write=100)])
    b = _Budget(p, MODEL, cap_usd=None, watch=PrefixWatch(expected={"generation": H}))
    b.call(MODEL, [], None, PARAMS)
    with pytest.raises(PrefixChanged):
        b.call(MODEL, [], None, PARAMS_B)
    assert p.calls == 1


def test_budget_without_cache_fields_disables_telemetry_with_a_reason(caplog):
    for provider in (Scripted([usage()] * 4, reports=False), NoCacheFields([usage()] * 4)):
        b = _Budget(provider, MODEL, cap_usd=None, watch=PrefixWatch())
        with caplog.at_level(logging.WARNING):
            for _ in range(4):
                b.call(MODEL, [], None, PARAMS)
        assert b.watch.enabled is False and "scripted" in b.watch.disabled_reason
    assert any("disabled" in m for m in caplog.messages)


def test_budget_keeps_the_spend_cap_and_the_cost_split():
    p = Scripted([usage(write=100, out=10), usage(read=100, out=10), usage(read=100, out=10)])
    b = _Budget(p, MODEL, cap_usd=0.0001, watch=PrefixWatch(model=MODEL))
    b.call(MODEL, [], None, PARAMS)
    with pytest.raises(SpendCapExceeded):
        b.call(MODEL, [], None, PARAMS)
    assert b.spent_usd == pytest.approx(cost(MODEL, usage(write=100, out=10)))
    assert b.watch.summary()["cost_split"]["total_usd"] == pytest.approx(b.spent_usd)
    assert _Budget(p, MODEL).watch is None   # no watch, no cap: a plain pass-through


# ---- provider interface and call records
def test_anthropic_provider_reports_cache_usage_only_when_the_fields_exist():
    p = AnthropicProvider(client=object())
    raw = {"usage": usage(write=5, read=6, inp=7, out=8)}
    assert p.cache_usage(raw) == {"cache_creation_input_tokens": 5, "cache_read_input_tokens": 6, "input_tokens": 7, "output_tokens": 8}
    assert p.cache_usage({"usage": {"input_tokens": 7, "output_tokens": 8}}) is None
    assert p.cache_usage({}) is None


def test_completion_and_call_record_carry_the_prefix_hash(tmp_path):
    llm = CachedLLM(Scripted([usage(write=1), usage()]), tmp_path)
    c = llm.complete(MODEL, [{"role": "user", "content": "x"}], temperature=None, sample_index=0, **PARAMS)
    assert c.prefix_hash == H and _call_record(c)["prefix_hash"] == H
    hit = llm.complete(MODEL, [{"role": "user", "content": "x"}], temperature=None, sample_index=0, **PARAMS)
    assert hit.cache_hit and hit.prefix_hash == H
    nb = llm.complete(MODEL, [{"role": "user", "content": "y"}], temperature=None, sample_index=0, max_tokens=5)
    assert nb.prefix_hash is None       # no breakpoint, no prefix (Cedar-track requests)


# ---- --plan
def test_estimate_tokens_uses_the_two_calibrations():
    assert CALIBRATION["schema_chars_per_token"] == pytest.approx(73110 / 34009, rel=1e-6)
    assert CALIBRATION["prose_chars_per_token"] == pytest.approx(1106 / 334, rel=1e-6)
    assert estimate_tokens("x" * 2150, "schema") == 1000 and estimate_tokens("x" * 3311, "prose") == 1000
    with pytest.raises(ValueError):
        estimate_tokens("x", "other")


def test_recorded_prefix_reads_only_generation_calls_with_this_prefix(tmp_path):
    runs = tmp_path / "runs"
    d = runs / "20261120T000000Z-temporal-clean-x" / "scn"
    (d / "naive" / "sample_00").mkdir(parents=True)
    (d / "sondera" / "sample_00").mkdir(parents=True)
    json.dump({"prefix_hash": H, "cache_hit": False, "usage": usage(write=35000, out=1000)}, (d / "naive" / "sample_00" / "response.json").open("w"))
    json.dump({"round": 1, "generation": {"prefix_hash": H, "cache_hit": True, "usage": usage(read=35000, out=3000)},
               "judge": {"prefix_hash": H_B, "cache_hit": False, "usage": usage(write=2400, out=50)}}, (d / "sondera" / "sample_00" / "round1.json").open("w"))
    json.dump({"round": 2, "generation": {"prefix_hash": H, "cache_hit": False, "usage": usage(read=35000, out=2000)},
               "judge": {"prefix_hash": H_B, "cache_hit": False, "usage": usage(read=2400, out=50)}}, (d / "sondera" / "sample_00" / "round2.json").open("w"))
    r = recorded_prefix(runs, H)
    assert r["prefix_tokens"] == 35000 and r["calls"] == 3 and r["output_tokens_mean"] == pytest.approx(2000) and r["run_ids"] == ["20261120T000000Z-temporal-clean-x"]
    j = recorded_prefix(runs, H_B)
    assert j["prefix_tokens"] == 2400 and j["calls"] == 2 and j["output_tokens_mean"] == 50
    assert recorded_prefix(runs, "0" * 64) is None
    assert recorded_prefix(tmp_path / "nowhere", H) is None


def test_plan_counts_sizes_and_costs(tmp_path):
    inp = load_dogwood_inputs(T01, intent="goal-level", arm="L1")
    ncfg, scfg = NaiveDogwoodConfig(MODEL), SonderaDogwoodConfig(MODEL)
    _, params = build_request(inp, ncfg)
    _, jparams = judge_request(inp, "x", scfg)
    r = plan(inp, ncfg, scfg, ["naive", "sondera"], 20, tmp_path / "runs")
    assert r["calls"] == {"generation": {"min": 20, "max": 60}, "judge": {"min": 20, "max": 60}}
    assert r["prefixes"]["generation"]["hash"] == prefix_hash(MODEL, params) and r["prefixes"]["judge"]["hash"] == prefix_hash(MODEL, jparams)
    g = r["prefixes"]["generation"]
    assert g["tokens_recorded"] is None and g["tokens"] == g["tokens_estimate"] and g["source"] == "estimate"
    assert g["chars"] == sum(len(b["text"]) for b in params["system"])
    u = r["uncached"]["generation"]
    assert u["blocks_after_breakpoint"] == [] and u["user_message"]["chars"] == len(f"{inp.intent.rstrip()}\n\n{dogwood.FINAL_LINE}")
    assert u["user_message"]["tokens"] == estimate_tokens(f"{inp.intent.rstrip()}\n\n{dogwood.FINAL_LINE}", "prose") and u["tokens"] == u["user_message"]["tokens"]
    assert r["output_tokens_mean"]["value"] == CALIBRATION["generation_output_tokens_mean"] and "L1-S" in r["output_tokens_mean"]["source"]
    p = PRICES[MODEL]
    out = r["output_tokens_mean"]["value"]
    gen_call = (u["tokens"] * p["input"] + out * p["output"]) / 1e6
    with_min = (g["tokens"] * p["cache_write_5m"] + 19 * g["tokens"] * p["cache_read"]) / 1e6 + 20 * gen_call
    jt = r["prefixes"]["judge"]["tokens"]
    ju = r["uncached"]["judge"]["tokens"]
    with_min += (jt * p["cache_write_5m"] + 19 * jt * p["cache_read"]) / 1e6 + 20 * (ju * p["input"] + r["judge_output_tokens"] * p["output"]) / 1e6
    assert r["cost_usd"]["with_cache"]["min"] == pytest.approx(with_min, rel=1e-6)
    without_min = 20 * ((g["tokens"] * p["cache_write_5m"]) / 1e6 + gen_call) + 20 * ((jt * p["cache_write_5m"] + ju * p["input"] + r["judge_output_tokens"] * p["output"]) / 1e6)
    assert r["cost_usd"]["without_cache"]["min"] == pytest.approx(without_min, rel=1e-6)
    assert r["cost_usd"]["with_cache"]["max"] > r["cost_usd"]["with_cache"]["min"] and r["cost_usd"]["without_cache"]["min"] > r["cost_usd"]["with_cache"]["min"]
    text = plan_text(r)
    assert "no API call" in text and g["hash"][:12] in text and "with cache hits" in text and "without cache hits" in text
    # naive only: no judge
    r2 = plan(inp, ncfg, scfg, ["naive"], 7, tmp_path / "runs")
    assert r2["calls"] == {"generation": {"min": 7, "max": 7}, "judge": {"min": 0, "max": 0}} and r2["prefixes"]["judge"] is None
    r3 = plan(inp, ncfg, scfg, ["sondera"], 7, tmp_path / "runs")
    assert r3["calls"] == {"generation": {"min": 7, "max": 21}, "judge": {"min": 7, "max": 21}}


def test_plan_prefers_recorded_token_counts(tmp_path):
    inp = load_dogwood_inputs(T01, intent="goal-level", arm="L1")
    ncfg, scfg = NaiveDogwoodConfig(MODEL), SonderaDogwoodConfig(MODEL)
    h = prefix_hash(MODEL, build_request(inp, ncfg)[1])
    d = tmp_path / "runs" / "20261120T000000Z-temporal-clean-x" / "scn" / "naive" / "sample_00"
    d.mkdir(parents=True)
    json.dump({"prefix_hash": h, "cache_hit": False, "usage": usage(write=90554, out=1324)}, (d / "response.json").open("w"))
    r = plan(inp, ncfg, scfg, ["naive"], 3, tmp_path / "runs")
    g = r["prefixes"]["generation"]
    assert g["tokens_recorded"] == 90554 and g["tokens"] == 90554 and g["source"].startswith("recorded")
    assert r["output_tokens_mean"] == {"value": 1324.0, "source": "recorded: 1 generation call(s) with this prefix in 20261120T000000Z-temporal-clean-x"}


def test_plan_cli_makes_no_run_folder(tmp_path):
    before = sorted(p.name for p in (ROOT / "runs").iterdir())
    cmd = [sys.executable, "-m", "pgi.runs.temporal_clean", "--plan", "--model", MODEL, "--n", "20", "--scenario", str(T01),
           "--intent", "goal-level", "--arm", "L1", "--runs-dir", str(tmp_path / "runs")]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stderr
    assert "no API call" in proc.stdout and "generation prefix" in proc.stdout and "with cache hits" in proc.stdout
    assert sorted(p.name for p in (ROOT / "runs").iterdir()) == before and not (tmp_path / "runs").exists()


@pytest.mark.skipif(shutil.which("cedar") is None, reason="cedar CLI not on PATH")
def test_config_records_prefix_hashes_and_watch_status(tmp_path, monkeypatch):
    """A tiny real run (fake provider, 1 sample, naive only): config.json carries the prefix hashes and the watch status;
    summary.json carries the cache telemetry; every call record has the prefix hash."""
    from pgi.runs import temporal_clean
    fake = Scripted([usage(write=100, out=10)] * 4)
    monkeypatch.setattr("pgi.llm.anthropic_provider.AnthropicProvider", lambda: fake)
    monkeypatch.setattr(sys, "argv", ["x", "--model", MODEL, "--n", "1", "--scenario", str(T01), "--intent", "goal-level", "--generators", "naive",
                                      "--label", "watchtest", "--cache", str(tmp_path / "cache"), "--runs-dir", str(tmp_path / "runs")])
    temporal_clean.main()
    run = next((tmp_path / "runs").iterdir())
    config = json.loads((run / "config.json").read_text())
    pc = config["request"]["prompt_cache"]
    assert pc["layout"] == "default" and pc["prefix_hashes"]["generation"] == prefix_hash(MODEL, build_request(load_dogwood_inputs(T01, intent="goal-level"), NaiveDogwoodConfig(MODEL))[1])
    assert pc["telemetry"]["enabled"] is True and pc["run_level_prefix_rule"] == "off (default layout)"
    rec = json.loads((run / "t01_close_after_approval" / "naive" / "sample_00" / "response.json").read_text())
    assert rec["prefix_hash"] == pc["prefix_hashes"]["generation"] and rec["cache_split"]["tokens"]["cache_write"] == 100
    summary = json.loads((run / "summary.json").read_text())
    assert summary["naive"]["cache"]["hit_rate"] == {"k": 0, "n": 1} and summary["naive"]["cache"]["cost_split"]["tokens"]["cache_write"] == 100
    assert "## Prompt cache" in (run / "summary.md").read_text()


def _e1_run(runs: Path, name: str, model: str, h: str, outs: list[int], key_prefix: str) -> None:
    run = runs / name
    (run / "C1").mkdir(parents=True)
    json.dump({"model": model}, (run / "config.json").open("w"))
    for i, out in enumerate(outs):
        d = run / "C1" / f"seed_{1000 + i}"
        d.mkdir()
        json.dump({"round": 1, "generation": {"key_hash": f"{key_prefix}{i}", "prefix_hash": h, "cache_hit": False, "usage": usage(read=35000, out=out)}},
                  (d / "round1.json").open("w"))


def test_recorded_prefix_and_model_means_read_the_e1_layout(tmp_path):
    runs = tmp_path / "runs"
    _e1_run(runs, "20261122T000000Z-e1-instances-a", "claude-haiku-5-5", "a" * 64, [9000, 11000], "k")
    _e1_run(runs, "20261122T000001Z-e1-instances-b", "claude-haiku-5-5", "b" * 64, [9000, 11000], "k")      # a replay of the same keys: not double counted
    _e1_run(runs, "20261122T000002Z-e1-instances-c", "claude-sonnet-5-5", "c" * 64, [1500], "s")
    r = recorded_prefix(runs, "a" * 64)
    assert r["prefix_tokens"] == 35000 and r["calls"] == 2 and r["output_tokens_mean"] == 10000
    m = recorded_output_mean(runs, "claude-haiku-5-5")
    assert m == {"mean": 10000.0, "calls": 2, "run_ids": ["20261122T000000Z-e1-instances-a", "20261122T000001Z-e1-instances-b"]}
    assert recorded_output_mean(runs, "claude-sonnet-5-5")["mean"] == 1500 and recorded_output_mean(runs, "claude-opus-5-5") is None
    assert recorded_output_mean(runs, "claude-haiku-5-5", "judge") is None


def test_plan_falls_back_to_the_models_recorded_mean_before_the_calibration(tmp_path):
    inp = load_dogwood_inputs(T01, intent="goal-level", arm="L1")
    haiku = "claude-haiku-5-5"
    ncfg, scfg = NaiveDogwoodConfig(haiku), SonderaDogwoodConfig(haiku)
    _e1_run(tmp_path / "runs", "20261122T000000Z-e1-instances-a", haiku, "a" * 64, [9000, 11000], "k")
    r = plan(inp, ncfg, scfg, ["naive"], 3, tmp_path / "runs")
    assert r["prefixes"]["generation"]["source"] == "estimate"    # no recorded call on THIS prefix
    assert r["output_tokens_mean"]["value"] == 10000 and r["output_tokens_mean"]["source"].startswith("recorded: 2 generation call(s) by claude-haiku-5-5 on other prefixes")
    r2 = plan(inp, NaiveDogwoodConfig(MODEL), SonderaDogwoodConfig(MODEL), ["naive"], 3, tmp_path / "runs")
    assert r2["output_tokens_mean"]["value"] == CALIBRATION["generation_output_tokens_mean"]   # nothing recorded for Sonnet here
