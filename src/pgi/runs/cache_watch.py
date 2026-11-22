"""Prompt-cache telemetry, circuit breaker, run-level prefix rule and the `--plan` estimate (Phase 3, 2026-11-20). No LLM.

Cache rules this relies on (https://platform.claude.com/docs/en/build-with-claude/prompt-caching, read 2026-11-20): a hit
needs a byte-identical prefix (tools, then system, then messages) up to a block carrying cache_control; an entry is written
only at the breakpoint; the default lifetime is 5 minutes, restarted by each request that uses the entry; an entry is readable
only after the first response has started; the thinking and effort settings are part of the prefix. The usage fields split
the prompt: cache_creation_input_tokens (written now) + cache_read_input_tokens (read) + input_tokens (after the breakpoint).

PrefixWatch (per process, keyed by pgi.llm.prefix.prefix_hash):
- circuit breaker: once a prefix has been written, a fresh call on it with cache_read_input_tokens == 0 is a MISS even if it
  writes again; three consecutive misses raise CacheBreakerTripped; only a read resets the counter; a single miss (the entry
  expired during a long generation) is logged and otherwise normal; a prefix never written never trips (logged);
- run-level rule (split layout): the run registers its expected prefix hashes up front; `before` raises PrefixChanged for any
  other prefix BEFORE the call is sent (per-prefix counting cannot see a prefix that changes on every call);
- sequential calls: `before` refuses a second call on a prefix whose first call is still in flight (ConcurrentPrefixCall);
- counts and cost split (write, read, uncached input, output) read through the provider interface (`cache_usage`); a provider
  that reports none disables all of this with a logged reason;
- deadline expiry (pgi.llm.deadline, 2026-11-22): an abandoned call is neither a hit nor a miss (no usage is observed); `expired`
  releases the in-flight guard, counts the expiry and resets the consecutive-miss counter, so the next call that writes the
  prefix again is one logged miss and not a breaker event.

`assumed_call_cost` (budget wrapper): the worst case a timed-out call could be billed, every system and message character at the
schema rate (the denser calibration) priced as a cache write plus `max_tokens` priced as output; added to the spend counter as
`assumed` so the cap stays conservative.

`plan` (no API call): generation and judge call counts (min / max over repair rounds), prefix hashes, the size of what is
cached and of what is not (part 2 and the user message), and the expected cost with and without cache hits. Token sizes are
the recorded `cache_creation_input_tokens` of an earlier call on the same prefix when one exists in the runs folder, else an
estimate from character counts calibrated on recorded runs (CALIBRATION): schema text on the L1-S run (73,110 static chars for
34,009 cached tokens), prose on the goal-level user message (1,106 chars for 334 tokens).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pgi.generators import dogwood
from pgi.generators.dogwood_inputs import DogwoodInputs
from pgi.llm.prefix import prefix_blocks, prefix_hash
from pgi.llm.pricing import PRICES, cost

log = logging.getLogger("pgi.cache")

CALIBRATION = {
    "schema_chars_per_token": 73110 / 34009,   # L1-S run: static prefix = instructions + reference + action schema + event schema
    "prose_chars_per_token": 1106 / 334,       # goal-level intent + final line (user message), recorded input_tokens
    "generation_output_tokens_mean": 1939.4,   # L1-S run, the 20 naive generation calls (judge calls excluded)
    "judge_output_tokens_mean": 646.9,         # L1-S run, 22 fresh judge calls
    "sources": {"schema_and_generation_output": "runs/20261118T233341Z-temporal-clean-t01-goal-level-L1-S (schema-only layout)",
                "prose": "runs/20261120T074222Z-temporal-clean-t01-goal-level-L10 naive sample_00 (same goal-level user message)"},
}
_SCHEMA_HEADINGS = ("## Action schema", "## Temporal event schema")
_CACHE_KEYS = ("cache_creation_input_tokens", "cache_read_input_tokens", "input_tokens", "output_tokens")


class CacheBreakerTripped(RuntimeError):
    """Three consecutive fresh calls on an already-written prefix read nothing from the cache."""


class PrefixChanged(RuntimeError):
    """A call's prefix hash is not one the run registered (split layout); raised before the call is sent."""


class ConcurrentPrefixCall(RuntimeError):
    """A second call on a prefix was started while its first call was still in flight."""


def cost_split(model: str, usage: dict) -> dict:
    """Tokens and USD per category (cache write, cache read, uncached input, output) from one usage dict or a sum of them."""
    p = PRICES[model]
    tokens = {"cache_write": int(usage.get("cache_creation_input_tokens") or 0), "cache_read": int(usage.get("cache_read_input_tokens") or 0),
              "uncached_input": int(usage.get("input_tokens") or 0), "output": int(usage.get("output_tokens") or 0)}
    usd = {"cache_write": tokens["cache_write"] * p["cache_write_5m"] / 1e6, "cache_read": tokens["cache_read"] * p["cache_read"] / 1e6,
           "uncached_input": tokens["uncached_input"] * p["input"] / 1e6, "output": tokens["output"] * p["output"] / 1e6}
    return {"tokens": tokens, "usd": usd, "total_usd": cost(model, usage)}


def _sum_usage(usages: list[dict]) -> dict:
    return {k: sum(int(u.get(k) or 0) for u in usages) for k in _CACHE_KEYS}


def _chars(x) -> int:
    """Characters of text in a system/messages value: a string, a block list ({"text": ...}), or a message list."""
    if isinstance(x, str):
        return len(x)
    if isinstance(x, dict):
        return _chars(x.get("text", "")) + _chars(x.get("content", ""))
    return sum(_chars(i) for i in x)


ASSUMED_OUTPUT_FALLBACK = 32000


def assumed_call_cost(model: str, messages: list[dict], params: dict) -> dict:
    """Worst-case cost of a call whose response never arrived (module doc): all input at the schema rate as a cache write, plus
    `max_tokens` (fallback ASSUMED_OUTPUT_FALLBACK when absent) as output."""
    chars = _chars(params.get("system", "")) + _chars(messages)
    tokens_in = round(chars / CALIBRATION["schema_chars_per_token"])
    max_tokens = params.get("max_tokens")
    out = int(max_tokens) if max_tokens else ASSUMED_OUTPUT_FALLBACK
    p = PRICES[model]
    basis = ("worst case: every input character at the schema rate (%.2f chars/token) priced as a cache write, plus max_tokens as output"
             % CALIBRATION["schema_chars_per_token"]) + ("" if max_tokens else f" (max_tokens absent: {ASSUMED_OUTPUT_FALLBACK} assumed)")
    return {"chars": chars, "input_tokens_assumed": tokens_in, "output_tokens_assumed": out,
            "usd": (tokens_in * p["cache_write_5m"] + out * p["output"]) / 1e6, "basis": basis}


class PrefixWatch:
    """Per-prefix cache telemetry and the circuit breaker (module doc). `expected`: name -> prefix hash the run registered."""

    def __init__(self, expected: dict[str, str] | None = None, threshold: int = 3, model: str | None = None) -> None:
        self.expected = dict(expected) if expected else None
        self.threshold, self.model = threshold, model
        self.prefixes: dict[str, dict] = {}
        self.in_flight: set[str] = set()
        self.disabled_reason: str | None = None
        self._usages: list[dict] = []

    @property
    def enabled(self) -> bool:
        return self.disabled_reason is None

    def disable(self, reason: str) -> None:
        if self.disabled_reason is None:
            self.disabled_reason = reason
            log.warning("prompt-cache telemetry and circuit breaker disabled: %s", reason)

    def before(self, prefix: str) -> None:
        """Checks that run before a call is sent: the registered-prefix rule and the in-flight guard."""
        if self.expected is not None and prefix not in self.expected.values():
            registered = ", ".join(f"{name} {h[:12]}" for name, h in self.expected.items())
            raise PrefixChanged(f"prefix {prefix[:12]} is not one this run registered ({registered}); the prompt prefix changed, "
                                "so every call would write a new cache entry: refusing to send the call")
        if prefix in self.in_flight:
            raise ConcurrentPrefixCall(f"a call on prefix {prefix[:12]} is still in flight; calls must be sequential "
                                       "(the first call on a prefix must complete before another is sent)")
        self.in_flight.add(prefix)

    def abort(self, prefix: str) -> None:
        """The call failed in transport: no usage to observe."""
        self.in_flight.discard(prefix)

    def _state(self, prefix: str) -> dict:
        return self.prefixes.setdefault(prefix, {"calls": 0, "writes": 0, "reads": 0, "misses": 0, "consecutive_misses": 0,
                                                 "max_consecutive_misses": 0, "written": False, "expiries": 0, "after_expiry": False})

    def expired(self, prefix: str) -> None:
        """The call hit the wall-clock deadline and was abandoned: no usage to observe, neither hit nor miss. Releases the
        in-flight guard; resets the consecutive-miss counter so the next write of the prefix is one logged miss, not a trip."""
        self.in_flight.discard(prefix)
        st = self._state(prefix)
        st["expiries"] += 1
        st["consecutive_misses"] = 0
        st["after_expiry"] = True
        log.warning("prefix %s: call abandoned at the deadline (expiry %d; neither hit nor miss; consecutive-miss counter reset)",
                    prefix[:12], st["expiries"])

    def after(self, prefix: str, cache_usage: dict | None) -> dict:
        """Observe one completed fresh call. Raises CacheBreakerTripped on the third consecutive miss."""
        self.in_flight.discard(prefix)
        st = self._state(prefix)
        st["calls"] += 1
        after_expiry = st["after_expiry"]
        st["after_expiry"] = False
        if cache_usage is None:
            self.disable("provider reports no cache usage fields")
        if not self.enabled:
            return {"prefix": prefix, "telemetry": "disabled", "miss": None, "consecutive_misses": None}
        self._usages.append(cache_usage)
        write, read = int(cache_usage.get("cache_creation_input_tokens") or 0), int(cache_usage.get("cache_read_input_tokens") or 0)
        st["writes"] += write > 0
        st["reads"] += read > 0
        miss = False
        if read > 0:
            st["consecutive_misses"] = 0
        elif st["written"]:
            miss = True
            st["misses"] += 1
            st["consecutive_misses"] += 1
            st["max_consecutive_misses"] = max(st["max_consecutive_misses"], st["consecutive_misses"])
            log.warning("cache miss on prefix %s: call %d read 0 cached tokens (%s); %d consecutive%s", prefix[:12], st["calls"],
                        f"re-wrote {write}" if write else "no write either", st["consecutive_misses"],
                        " (first call after an expiry; expected, not a breaker event by itself)" if after_expiry else "")
        elif write == 0:
            log.warning("prefix %s: no cache write and no cache read on call %d (prefix never written; not counted as a miss)",
                        prefix[:12], st["calls"])
        if write > 0:
            st["written"] = True
        if miss and st["consecutive_misses"] >= self.threshold:
            raise CacheBreakerTripped(f"{st['consecutive_misses']} consecutive calls on prefix {prefix[:12]} read 0 cached tokens after it "
                                      f"was written ({st['calls']} calls: {st['writes']} writes, {st['reads']} reads); the prompt cache is not "
                                      "being hit, stopping the run")
        return {"prefix": prefix, "telemetry": "ok", "miss": miss, "consecutive_misses": st["consecutive_misses"],
                "cache_creation_input_tokens": write, "cache_read_input_tokens": read}

    def summary(self) -> dict:
        reads = sum(1 for u in self._usages if int(u.get("cache_read_input_tokens") or 0) > 0)
        return {"enabled": self.enabled, "disabled_reason": self.disabled_reason, "expected": self.expected, "threshold": self.threshold,
                "hit_rate": {"k": reads, "n": len(self._usages)}, "expiries": sum(st["expiries"] for st in self.prefixes.values()),
                "cost_split": cost_split(self.model, _sum_usage(self._usages)) if self.model else None,
                "prefixes": {h: dict(st) for h, st in self.prefixes.items()}}


# ---- --plan
def estimate_tokens(text: str, kind: str) -> int:
    """Token estimate from characters: `schema` (dense Cedar/Dogwood schema text) or `prose`, calibrated on recorded runs."""
    if kind not in ("schema", "prose"):
        raise ValueError(f"kind must be schema or prose, got {kind!r}")
    return round(len(text) / CALIBRATION[f"{kind}_chars_per_token"])


def _kind(text: str) -> str:
    return "schema" if text.startswith(_SCHEMA_HEADINGS) else "prose"


def _block_report(b: dict) -> dict:
    return {"heading": b["text"].splitlines()[0][:60], "kind": _kind(b["text"]), "chars": len(b["text"]), "tokens": estimate_tokens(b["text"], _kind(b["text"]))}


def recorded_prefix(runs_dir: Path, h: str) -> dict | None:
    """Recorded calls on this prefix in the runs folder: the prefix's token count (a cache write, else a read), the number
    of calls and their mean output tokens, and the run ids. None when no call record carries the hash."""
    runs_dir = Path(runs_dir)
    if not runs_dir.is_dir():
        return None
    recs: list[tuple[str, dict]] = []
    for run in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        for p in run.glob("*/*/sample_*/response.json"):
            r = json.loads(p.read_text())
            if r.get("prefix_hash") == h:
                recs.append((run.name, r.get("usage") or {}))
        for p in run.glob("*/*/sample_*/round*.json"):
            r = json.loads(p.read_text())
            for part in ("generation", "judge"):
                c = r.get(part) or {}
                if c.get("prefix_hash") == h:
                    recs.append((run.name, c.get("usage") or {}))
    if not recs:
        return None
    writes = [int(u["cache_creation_input_tokens"]) for _, u in recs if u.get("cache_creation_input_tokens")]
    reads = [int(u["cache_read_input_tokens"]) for _, u in recs if u.get("cache_read_input_tokens")]
    outs = [int(u.get("output_tokens") or 0) for _, u in recs]
    return {"prefix_tokens": writes[0] if writes else (reads[0] if reads else None), "calls": len(recs),
            "output_tokens_mean": sum(outs) / len(outs), "run_ids": sorted({r for r, _ in recs})}


def _prefix_report(model: str, params: dict, runs_dir: Path) -> tuple[dict, dict | None]:
    h = prefix_hash(model, params)
    blocks = [_block_report(b) for b in prefix_blocks(params)]
    est = sum(b["tokens"] for b in blocks)
    rec = recorded_prefix(runs_dir, h)
    recorded = rec["prefix_tokens"] if rec else None
    return {"hash": h, "chars": sum(b["chars"] for b in blocks), "tokens_estimate": est, "tokens_recorded": recorded,
            "tokens": recorded if recorded else est,
            "source": f"recorded run(s) {', '.join(rec['run_ids'])}" if recorded else "estimate", "blocks": blocks}, rec


def _uncached(params: dict, user_content: str) -> dict:
    after = [_block_report(b) for b in params["system"][len(prefix_blocks(params)):]]
    user = {"chars": len(user_content), "tokens": estimate_tokens(user_content, "prose")}
    return {"blocks_after_breakpoint": after, "user_message": user, "tokens": sum(b["tokens"] for b in after) + user["tokens"]}


def _cost(model: str, prefix_tokens: int, uncached: int, out: float, calls: int, cached: bool) -> float:
    if calls == 0:
        return 0.0
    p = PRICES[model]
    per_call = (uncached * p["input"] + out * p["output"]) / 1e6
    if cached:
        prefix = (prefix_tokens * p["cache_write_5m"] + (calls - 1) * prefix_tokens * p["cache_read"]) / 1e6
    else:
        prefix = calls * prefix_tokens * p["cache_write_5m"] / 1e6
    return prefix + calls * per_call


def plan(inputs: DogwoodInputs, ncfg: dogwood.NaiveDogwoodConfig, scfg: dogwood.SonderaDogwoodConfig, generators: list[str], n: int,
         runs_dir: Path) -> dict:
    """The `--plan` report (module doc). Builds the requests exactly as a run would; sends nothing."""
    model = ncfg.model
    messages, params = dogwood.build_request(inputs, ncfg)
    gen, rec = _prefix_report(model, params, runs_dir)
    uncached_gen = _uncached(params, messages[0]["content"])
    if rec:
        out_mean = {"value": rec["output_tokens_mean"], "source": f"recorded: {rec['calls']} generation call(s) with this prefix in {', '.join(rec['run_ids'])}"}
    else:
        out_mean = {"value": CALIBRATION["generation_output_tokens_mean"],
                    "source": f"estimate: mean output tokens of the naive generation calls of the L1-S run ({CALIBRATION['sources']['schema_and_generation_output']})"}
    has_sondera, has_naive = "sondera" in generators, "naive" in generators
    rounds = scfg.max_rounds
    gen_min = n if (has_naive or has_sondera) else 0
    gen_max = n + (rounds - 1) * n if has_sondera else gen_min
    judge_min, judge_max = (n, rounds * n) if has_sondera else (0, 0)
    judge = uncached_judge = None
    judge_out = 0.0
    if has_sondera:
        jm, jp = dogwood.judge_request(inputs, "", scfg)
        judge, jrec = _prefix_report(model, jp, runs_dir)
        base = _uncached(jp, jm[0]["content"])
        policy_tokens = round(out_mean["value"])   # the policy under review stands in at one generation's output size
        uncached_judge = {**base, "policy_tokens_assumed": policy_tokens, "tokens": base["tokens"] + policy_tokens}
        judge_out = jrec["output_tokens_mean"] if jrec else CALIBRATION["judge_output_tokens_mean"]
    out = out_mean["value"]
    with_cache = {k: _cost(model, gen["tokens"], uncached_gen["tokens"], out, g, True) +
                  (_cost(model, judge["tokens"], uncached_judge["tokens"], judge_out, j, True) if judge else 0.0)
                  for k, g, j in (("min", gen_min, judge_min), ("max", gen_max, judge_max))}
    without = {k: _cost(model, gen["tokens"], uncached_gen["tokens"], out, g, False) +
               (_cost(model, judge["tokens"], uncached_judge["tokens"], judge_out, j, False) if judge else 0.0)
               for k, g, j in (("min", gen_min, judge_min), ("max", gen_max, judge_max))}
    return {"model": model, "n": n, "generators": list(generators), "layout": ncfg.layout, "max_rounds": rounds,
            "calls": {"generation": {"min": gen_min, "max": gen_max}, "judge": {"min": judge_min, "max": judge_max}},
            "prefixes": {"generation": gen, "judge": judge}, "uncached": {"generation": uncached_gen, "judge": uncached_judge},
            "output_tokens_mean": out_mean, "judge_output_tokens": judge_out,
            "cost_usd": {"with_cache": with_cache, "without_cache": without}, "calibration": CALIBRATION}


def plan_text(r: dict) -> str:
    g, j, ug, uj = r["prefixes"]["generation"], r["prefixes"]["judge"], r["uncached"]["generation"], r["uncached"]["judge"]
    lines = [f"plan (no API call): model {r['model']}, N={r['n']}, generators {', '.join(r['generators'])}, layout {r['layout']}, "
             f"max rounds {r['max_rounds']}",
             f"calls: generation {r['calls']['generation']['min']}-{r['calls']['generation']['max']}, judge {r['calls']['judge']['min']}-{r['calls']['judge']['max']}",
             f"generation prefix {g['hash']}: {g['tokens']} tokens ({g['source']}; estimate {g['tokens_estimate']} from {g['chars']} chars in "
             f"{len(g['blocks'])} block(s): " + "; ".join(f"{b['heading']!r} {b['chars']} chars ~{b['tokens']} {b['kind']}" for b in g["blocks"]) + ")"]
    if j:
        lines.append(f"judge prefix {j['hash']}: {j['tokens']} tokens ({j['source']}; estimate {j['tokens_estimate']} from {j['chars']} chars)")
    after = "; ".join(f"{b['heading']!r} {b['chars']} chars ~{b['tokens']} tokens" for b in ug["blocks_after_breakpoint"]) or "none"
    lines.append(f"uncached per generation call: blocks after the breakpoint: {after}; user message {ug['user_message']['chars']} chars "
                 f"~{ug['user_message']['tokens']} tokens; total ~{ug['tokens']} tokens")
    if uj:
        lines.append(f"uncached per judge call: ~{uj['tokens']} tokens (intent {uj['user_message']['tokens']} + policy assumed {uj['policy_tokens_assumed']})")
    lines.append(f"output tokens per generation call: {r['output_tokens_mean']['value']:.0f} ({r['output_tokens_mean']['source']})"
                 + (f"; per judge call: {r['judge_output_tokens']:.0f}" if j else ""))
    c = r["cost_usd"]
    lines.append(f"expected cost with cache hits: ${c['with_cache']['min']:.2f} to ${c['with_cache']['max']:.2f}; "
                 f"without cache hits (every call writes the prefix): ${c['without_cache']['min']:.2f} to ${c['without_cache']['max']:.2f}")
    return "\n".join(lines)
