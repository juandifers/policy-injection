"""The wall-clock deadline around every provider call (pgi.llm.deadline), its effect on the budget wrapper and the
PrefixWatch, the shared retry-on-expiry helper (pgi.runs.attempts), and the temporal runner end to end with a provider stub
that sleeps. No API call anywhere."""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path

import pytest

from pgi.generators.dogwood import NaiveDogwoodConfig, build_request
from pgi.generators.dogwood_inputs import load_dogwood_inputs
from pgi.llm.cache import CachedLLM
from pgi.llm.deadline import CallDeadlineExceeded, DeadlineProvider
from pgi.llm.prefix import prefix_hash
from pgi.llm.pricing import PRICES
from pgi.runs.attempts import DeadlineRunStopped, run_sample_with_retries
from pgi.runs.cache_watch import CALIBRATION, CacheBreakerTripped, PrefixWatch, assumed_call_cost
from pgi.runs.temporal_clean import _Budget

T01 = Path(__file__).resolve().parents[1] / "domains/assetopsbench/scenarios/t01_close_after_approval"
MODEL = "claude-haiku-5-5"
PARAMS = {"system": [{"type": "text", "text": "## Action schema\nnamespace X {}", "cache_control": {"type": "ephemeral"}}], "max_tokens": 1000}
H = prefix_hash(MODEL, PARAMS)
DEADLINE = 0.05   # seconds; the stub sleeps 4x longer on a hang


def usage(write=0, read=0, inp=300, out=1000) -> dict:
    return {"cache_creation_input_tokens": write, "cache_read_input_tokens": read, "input_tokens": inp, "output_tokens": out}


class Sleeper:
    """Provider stub. Each call pops (delay_s, text, usage); sleeps `delay_s` in the calling thread, then returns. `finished`
    is set after every call completes (late ones included) so a test can wait for an abandoned call to return."""

    name = "sleeper"

    def __init__(self, script):
        self.script, self.calls, self.completed = list(script), 0, 0
        self.finished = threading.Condition()
        self.judge_text = "NO MISMATCHES"

    def call(self, model, messages, temperature, params):
        self.calls += 1
        delay, text, u = self.script.pop(0)
        time.sleep(delay)
        if "policy reviewer" in params["system"][0]["text"]:
            text = self.judge_text
        raw = {"model": f"{model}-v1", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "usage": u}
        with self.finished:
            self.completed += 1
            self.finished.notify_all()
        return raw

    def wait_until_completed(self, n, timeout=5.0):
        with self.finished:
            assert self.finished.wait_for(lambda: self.completed >= n, timeout), f"only {self.completed} of {n} calls completed"

    def text(self, raw):
        return raw["content"][0]["text"]

    def model_version(self, raw):
        return raw["model"]

    def usage(self, raw):
        return raw["usage"]

    def request_settings(self):
        return {"timeout_s": 300.0, "max_retries": 2}

    def cache_usage(self, raw):
        u = raw["usage"]
        return {k: u.get(k, 0) for k in ("cache_creation_input_tokens", "cache_read_input_tokens", "input_tokens", "output_tokens")}


def fast(text="permit (principal, action, resource);", u=None):
    return (0.0, text, u or usage(read=500))


def hang(text="LATE", u=None):
    return (4 * DEADLINE, text, u or usage(write=500))


# ---- DeadlineProvider
def test_expiry_raises_the_typed_error_near_the_deadline():
    inner = Sleeper([hang()])
    dp = DeadlineProvider(inner, seconds=DEADLINE)
    t0 = time.monotonic()
    with pytest.raises(CallDeadlineExceeded) as ei:
        dp.call(MODEL, [{"role": "user", "content": "x"}], None, PARAMS)
    elapsed = time.monotonic() - t0
    assert DEADLINE <= elapsed < 3 * DEADLINE, elapsed
    e = ei.value
    assert e.deadline_s == DEADLINE and e.elapsed_s >= DEADLINE and e.model == MODEL and e.prefix_hash == H
    assert e.event["deadline_s"] == DEADLINE and e.event["prefix_hash"] == H and e.event["late_usage"] is None
    assert dp.expiries == [e.event] and dp.request_settings() == {"timeout_s": 300.0, "max_retries": 2, "deadline_s": DEADLINE}


def test_a_call_within_the_deadline_returns_normally_and_records_no_event():
    inner = Sleeper([fast("OK")])
    dp = DeadlineProvider(inner, seconds=DEADLINE)
    raw = dp.call(MODEL, [], None, PARAMS)
    assert dp.text(raw) == "OK" and dp.expiries == [] and dp.usage(raw) == usage(read=500) and dp.model_version(raw) == f"{MODEL}-v1"


def test_an_exception_inside_the_deadline_propagates_unchanged():
    class Boom(Sleeper):
        def call(self, *a):
            raise ConnectionError("reset")
    with pytest.raises(ConnectionError, match="reset"):
        DeadlineProvider(Boom([]), seconds=DEADLINE).call(MODEL, [], None, PARAMS)


def test_late_result_is_discarded_never_cached_and_its_usage_lands_in_the_event(tmp_path):
    """First call hangs and returns LATE after the deadline; the retry returns FRESH. The cache holds one entry: FRESH. Once
    the abandoned call returns, its usage is written into the expiry event (best effort billing evidence)."""
    inner = Sleeper([hang("LATE", usage(write=777, out=99)), fast("FRESH")])
    dp = DeadlineProvider(inner, seconds=DEADLINE)
    llm = CachedLLM(dp, tmp_path / "cache")
    msgs = [{"role": "user", "content": "x"}]
    with pytest.raises(CallDeadlineExceeded):
        llm.complete(MODEL, msgs, temperature=None, sample_index=0, **PARAMS)
    c = llm.complete(MODEL, msgs, temperature=None, sample_index=0, **PARAMS)
    assert c.text == "FRESH" and not c.cache_hit and llm.api_calls == 1
    inner.wait_until_completed(2)   # the abandoned call has now returned inside its thread
    entries = list((tmp_path / "cache").rglob("*.json"))
    assert len(entries) == 1 and json.loads(entries[0].read_text())["text"] == "FRESH"
    ev = dp.expiries[0]
    assert ev["late_usage"] == usage(write=777, out=99) and ev["late_elapsed_s"] >= 4 * DEADLINE
    assert llm.complete(MODEL, msgs, temperature=None, sample_index=0, **PARAMS).cache_hit and llm.api_calls == 1


def test_deadline_must_be_positive():
    with pytest.raises(ValueError):
        DeadlineProvider(Sleeper([]), seconds=0)


# ---- assumed worst-case cost of an abandoned call
def test_assumed_cost_is_every_character_at_the_schema_rate_as_a_cache_write_plus_max_tokens_output():
    params = {"system": [{"type": "text", "text": "a" * 215}, {"type": "text", "text": "b" * 215}], "max_tokens": 1000}
    messages = [{"role": "user", "content": "c" * 215}, {"role": "assistant", "content": [{"type": "text", "text": "d" * 215}]}]
    a = assumed_call_cost(MODEL, messages, params)
    p = PRICES[MODEL]
    assert a["input_tokens_assumed"] == round(4 * 215 / CALIBRATION["schema_chars_per_token"]) == 400 and a["output_tokens_assumed"] == 1000
    assert a["chars"] == 4 * 215
    assert a["usd"] == pytest.approx((400 * p["cache_write_5m"] + 1000 * p["output"]) / 1e6)
    assert a["basis"].startswith("worst case")


def test_assumed_cost_without_max_tokens_falls_back_and_says_so():
    a = assumed_call_cost(MODEL, [], {"system": "x" * 43})
    assert a["input_tokens_assumed"] == 20 and a["output_tokens_assumed"] == 32000 and "max_tokens absent" in a["basis"]


# ---- PrefixWatch and _Budget after an expiry
def test_watch_expiry_is_neither_hit_nor_miss_releases_the_guard_and_resets_the_counter(caplog):
    w = PrefixWatch(model=MODEL)
    w.before(H); w.after(H, usage(write=100))
    w.before(H); w.after(H, usage(write=100))        # miss 1
    w.before(H); w.after(H, usage(write=100))        # miss 2
    assert w.prefixes[H]["consecutive_misses"] == 2
    w.before(H)
    with caplog.at_level(logging.WARNING, logger="pgi.cache"):
        w.expired(H)
    assert H not in w.in_flight and "deadline" in caplog.text
    st = w.prefixes[H]
    assert st["expiries"] == 1 and st["consecutive_misses"] == 0 and st["calls"] == 3 and st["misses"] == 2
    assert w.summary()["hit_rate"] == {"k": 0, "n": 3} and w.summary()["expiries"] == 1
    # the call after the expiry writes again: one logged miss, not a breaker event
    w.before(H)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="pgi.cache"):
        r = w.after(H, usage(write=100))
    assert (r["miss"], r["consecutive_misses"]) == (True, 1) and "after an expiry" in caplog.text
    assert st["misses"] == 3 and w.summary()["hit_rate"] == {"k": 0, "n": 4}
    w.before(H); w.after(H, usage(write=100))
    with pytest.raises(CacheBreakerTripped):                    # the breaker still works afterwards: 3 fresh consecutive misses
        w.before(H); w.after(H, usage(write=100))


def test_watch_expiry_on_a_prefix_never_called_is_recorded():
    w = PrefixWatch(model=MODEL)
    w.before(H)
    w.expired(H)
    assert w.prefixes[H]["expiries"] == 1 and w.prefixes[H]["calls"] == 0 and w.prefixes[H]["written"] is False


def test_budget_on_expiry_releases_the_watch_adds_the_assumed_cost_and_reraises():
    inner = Sleeper([hang(), fast()])
    w = PrefixWatch(model=MODEL)
    b = _Budget(DeadlineProvider(inner, seconds=DEADLINE), MODEL, cap_usd=None, watch=w)
    with pytest.raises(CallDeadlineExceeded) as ei:
        b.call(MODEL, [{"role": "user", "content": "x" * 215}], None, PARAMS)
    a = assumed_call_cost(MODEL, [{"role": "user", "content": "x" * 215}], PARAMS)
    assert b.spent_usd == pytest.approx(a["usd"]) and b.assumed_usd == pytest.approx(a["usd"]) and b.observed_usd == 0
    assert b.calls == 0 and b.expiries == 1 and ei.value.event["assumed_usd"] == pytest.approx(a["usd"])
    assert H not in w.in_flight and w.prefixes[H]["expiries"] == 1 and w.summary()["hit_rate"]["n"] == 0
    raw = b.call(MODEL, [{"role": "user", "content": "x"}], None, PARAMS)
    assert b.calls == 1 and b.observed_usd > 0 and b.spent_usd == pytest.approx(b.observed_usd + b.assumed_usd)
    assert b.spend() == {"spent_usd": b.spent_usd, "observed_usd": b.observed_usd, "assumed_usd": b.assumed_usd, "calls": 1, "expiries": 1}
    assert b.text(raw).startswith("permit")


def test_budget_assumed_cost_counts_toward_the_cap():
    inner = Sleeper([hang(), fast()])
    b = _Budget(DeadlineProvider(inner, seconds=DEADLINE), MODEL, cap_usd=1e-9)
    with pytest.raises(CallDeadlineExceeded):
        b.call(MODEL, [{"role": "user", "content": "x"}], None, PARAMS)
    from pgi.runs.temporal_clean import SpendCapExceeded
    with pytest.raises(SpendCapExceeded):
        b.call(MODEL, [{"role": "user", "content": "x"}], None, PARAMS)
    assert inner.calls == 1


# ---- the shared retry helper
def _attempts(outcomes):
    """A 'run one sample' callable that raises CallDeadlineExceeded for each 'X' in outcomes, then returns the string."""
    it = iter(outcomes)

    def fn(attempt):
        o = next(it)
        if o == "X":
            inner = Sleeper([hang()])
            DeadlineProvider(inner, seconds=DEADLINE).call(MODEL, [], None, PARAMS)
        return o
    return fn


def test_helper_returns_the_first_result_and_tags_each_expiry_event():
    result, events = run_sample_with_retries(_attempts(["X", "X", "ok"]), generator="naive", sample=3)
    assert result == "ok" and [e["attempt"] for e in events] == [1, 2]
    assert all(e["generator"] == "naive" and e["sample"] == 3 and e["deadline_s"] == DEADLINE for e in events)
    assert run_sample_with_retries(_attempts(["ok"]), generator="naive", sample=0) == ("ok", [])
    seen = []

    def fn(attempt):
        seen.append(attempt)
        if attempt == 1:
            _attempts(["X"])(1)          # first attempt expires
        return attempt
    assert run_sample_with_retries(fn, generator="naive", sample=0)[0] == 2 and seen == [1, 2]


def test_helper_stops_after_the_third_expiry_with_the_events_attached():
    with pytest.raises(DeadlineRunStopped) as ei:
        run_sample_with_retries(_attempts(["X", "X", "X", "ok"]), generator="sondera", sample=1)
    assert [e["attempt"] for e in ei.value.events] == [1, 2, 3] and ei.value.generator == "sondera" and ei.value.sample == 1
    assert "3 attempts" in str(ei.value)


def test_helper_max_retries_is_configurable_and_other_errors_pass_through():
    with pytest.raises(DeadlineRunStopped) as ei:
        run_sample_with_retries(_attempts(["X", "ok"]), generator="naive", sample=0, max_retries=0)
    assert len(ei.value.events) == 1

    def boom(attempt):
        raise ValueError("not a deadline")
    with pytest.raises(ValueError, match="not a deadline"):
        run_sample_with_retries(boom, generator="naive", sample=0)


# ---- the temporal runner end to end
GOLD = (T01 / "gold.dw").read_text()


def _main(tmp_path, monkeypatch, stub, n, label, deadline=DEADLINE):
    from pgi.runs import temporal_clean
    monkeypatch.setattr("pgi.llm.anthropic_provider.AnthropicProvider", lambda: stub)
    monkeypatch.setattr(sys, "argv", ["x", "--model", MODEL, "--n", str(n), "--scenario", str(T01), "--intent", "goal-level",
                                      "--generators", "naive", "--label", label, "--cache", str(tmp_path / "cache"),
                                      "--runs-dir", str(tmp_path / "runs"), "--deadline-s", str(deadline)])
    temporal_clean.main()


def _policy(text=GOLD):
    return "```dogwood\n" + text + "```"


def test_runner_keeps_a_sample_that_succeeded_after_two_expiries_and_records_everything(tmp_path, monkeypatch):
    stub = Sleeper([fast(_policy(), usage(write=900)), hang(_policy("permit {}"), usage(write=900, out=5)),
                    hang(_policy("permit {}"), usage(write=900, out=5)), fast(_policy(), usage(read=900))])
    _main(tmp_path, monkeypatch, stub, n=2, label="two-expiries")
    (run,) = (tmp_path / "runs").iterdir()
    assert not run.name.startswith(".tmp-")
    cfg = json.loads((run / "config.json").read_text())
    assert cfg["request"]["transport"] == {"timeout_s": 300.0, "max_retries": 2, "deadline_s": DEADLINE}
    assert cfg["request"]["deadline"] == {"seconds": DEADLINE, "retries_on_expiry": 2,
                                          "rule": "a sample whose call expires is retried with the same request up to twice; after the third expiry the run stops; "
                                                  "a sample that succeeded after one or two expiries is a normal sample; a late result is never cached"}
    s1 = run / "t01_close_after_approval" / "naive" / "sample_01"
    rec = json.loads((s1 / "response.json").read_text())
    assert rec["deadline_s"] == DEADLINE and rec["expiries_before"] == 2 and rec["text"] == _policy() and rec["cache_hit"] is False
    rec0 = json.loads((run / "t01_close_after_approval" / "naive" / "sample_00" / "response.json").read_text())
    assert rec0["expiries_before"] == 0
    ev = json.loads((s1 / "deadline.json").read_text())
    assert [e["attempt"] for e in ev] == [1, 2] and all(e["sample"] == 1 and e["generator"] == "naive" and e["assumed_usd"] > 0 for e in ev)
    events = json.loads((run / "deadline_events.json").read_text())
    assert len(events) == 2 and all(e["late_usage"] == usage(write=900, out=5) for e in events), events   # both abandoned calls returned during scoring
    summary = json.loads((run / "summary.json").read_text())["naive"]
    assert summary["n"] == 2 and summary["valid"] == 2 and summary["deadline_expiries"] == 2 and summary["samples_retried_after_expiry"] == [1]
    assert summary["api_calls"] == 2 and summary["cache"]["hit_rate"] == {"k": 1, "n": 2}
    md = (run / "summary.md").read_text()
    assert "## Deadline" in md and "| naive | 2 | 1 |" in md
    watch = json.loads((run / "cache_watch.json").read_text())
    assert watch["expiries"] == 2 and watch["hit_rate"] == {"k": 1, "n": 2}
    spend = json.loads((run / "spend.json").read_text())
    assert spend["expiries"] == 2 and spend["assumed_usd"] > 0 and spend["spent_usd"] == pytest.approx(spend["observed_usd"] + spend["assumed_usd"])
    assert len(list((tmp_path / "cache").rglob("*.json"))) == 2   # one entry per sample index


def test_runner_stops_after_three_expiries_and_a_resumed_run_makes_no_duplicate_sample(tmp_path, monkeypatch):
    stub = Sleeper([fast(_policy(), usage(write=900)), hang(), hang(), hang(), fast(_policy())])
    with pytest.raises(DeadlineRunStopped) as ei:
        _main(tmp_path, monkeypatch, stub, n=3, label="stopped")
    assert ei.value.sample == 1 and len(ei.value.events) == 3
    (tmp,) = (tmp_path / "runs").iterdir()
    assert tmp.name.startswith(".tmp-") and "DeadlineRunStopped" in (tmp / "FAILED").read_text()
    events = json.loads((tmp / "deadline_events.json").read_text())
    assert [e["attempt"] for e in events] == [1, 2, 3] and all(e["sample"] == 1 for e in events)
    assert stub.calls == 4 and len(list((tmp_path / "cache").rglob("*.json"))) == 1    # sample 0 cached; nothing from the hung calls
    stub.wait_until_completed(4)                                                          # the three abandoned calls return...
    assert len(list((tmp_path / "cache").rglob("*.json"))) == 1                          # ...and are still not cached
    # resume: same arguments, fresh provider; sample 0 replays, samples 1 and 2 are the only fresh calls
    stub2 = Sleeper([fast(_policy(), usage(read=900)), fast(_policy(), usage(read=900))])
    _main(tmp_path, monkeypatch, stub2, n=3, label="resumed")
    (run,) = [p for p in (tmp_path / "runs").iterdir() if not p.name.startswith(".tmp-")]
    summary = json.loads((run / "summary.json").read_text())["naive"]
    assert summary["n"] == 3 and summary["api_calls"] == 2 and stub2.calls == 2 and summary["deadline_expiries"] == 0
    recs = [json.loads((run / "t01_close_after_approval" / "naive" / f"sample_{i:02d}" / "response.json").read_text()) for i in range(3)]
    assert [r["cache_hit"] for r in recs] == [True, False, False] and len({r["key_hash"] for r in recs}) == 3
    entries = list((tmp_path / "cache").rglob("*.json"))
    assert len(entries) == 3 and len({json.loads(p.read_text())["key_hash"] for p in entries}) == 3   # exactly one generation per sample index


def test_cache_only_run_records_no_deadline(tmp_path, monkeypatch):
    from pgi.runs import temporal_clean
    stub = Sleeper([fast(_policy(), usage(write=900))])
    _main(tmp_path, monkeypatch, stub, n=1, label="seed")
    monkeypatch.setattr(sys, "argv", ["x", "--model", MODEL, "--n", "1", "--scenario", str(T01), "--intent", "goal-level", "--generators", "naive",
                                      "--label", "replay", "--cache", str(tmp_path / "cache"), "--runs-dir", str(tmp_path / "runs"), "--cache-only"])
    temporal_clean.main()
    run = next(p for p in (tmp_path / "runs").iterdir() if p.name.endswith("replay"))
    cfg = json.loads((run / "config.json").read_text())
    assert cfg["request"]["transport"] is None and cfg["request"]["deadline"]["seconds"] is None
    rec = json.loads((run / "t01_close_after_approval" / "naive" / "sample_00" / "response.json").read_text())
    assert rec["deadline_s"] is None and rec["expiries_before"] == 0 and rec["cache_hit"] is True


def test_default_deadline_is_600_s():
    from pgi.llm.deadline import DEFAULT_DEADLINE_S
    assert DEFAULT_DEADLINE_S == 600.0 and DeadlineProvider(Sleeper([])).seconds == 600.0
