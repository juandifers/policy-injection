"""Temporal clean runs: N Dogwood samples per generator for one temporal scenario, scored by pgi.oracle.temporal over the
scenario's trace suite, written to runs/<id>/.

    uv run --group dogwood python -m pgi.runs.temporal_clean --model claude-sonnet-5-5 --n 20 \
        --scenario domains/assetopsbench/scenarios/t01_close_after_approval --label t01
    ... --intent goal-level --arm L1       # selectable intent arm and manifest arm (scenario.yaml `intents`, `arms`)
    ... --input-mode schema-only           # Phase 2c L1-S: intent + generated schema only, no manifest text (default: manifests)
    ... --cache-only            # every LLM call must hit the cache (re-score; zero API calls)
    ... --spend-cap-usd 15      # stop (run fails loudly, samples so far stay cached) before a call would exceed the cap
    ... --layout split          # Phase 3: one cached prefix shared by every instance/cell/round (scenario needs `prompt_schema_base`)
    ... --contract-block        # Phase 3 D4: the trusted evidence-authority contract as the last system block (split layout only)
    ... --plan                  # no API call, no run folder: call counts, prefix hashes, sizes and expected cost (pgi.runs.cache_watch)
    ... --deadline-s 600        # wall-clock deadline around every API call, enforced outside the SDK (pgi.llm.deadline; default 600)

Deadline (2026-11-22; pgi.llm.deadline, pgi.runs.attempts): every provider call runs under a wall-clock deadline outside the SDK.
An expired call raises; the sample is attempted again with the same request up to twice; after the third expiry the run stops
(DeadlineRunStopped; the `.tmp-` folder stays with FAILED and `deadline_events.json`; a rerun with the same arguments replays every
finished sample from the cache). A late result is never returned and never cached, so every sample index has exactly one
generation; if it does arrive its usage is written into the event (`late_usage`, best effort). A sample that succeeded after one
or two expiries is a normal sample. Recorded: config `request.transport.deadline_s` and `request.deadline`; call records
`deadline_s` and `expiries_before`; per sample `deadline.json`; run-level `deadline_events.json` and `spend.json` (observed vs
assumed USD: an abandoned call is charged its worst case, pgi.runs.cache_watch.assumed_call_cost); summary `deadline_expiries`.
For the PrefixWatch an expiry is neither hit nor miss (cache_watch module doc).

Phase 3 additions (2026-11-20; pgi.runs.cache_watch): every call record carries `prefix_hash` (pgi.llm.prefix: model + system
blocks up to the cache breakpoint + thinking + effort) and `cache_split` (tokens and USD by cache write / cache read / uncached
input / output); config.json records the generator and judge prefix hashes under `request.prompt_cache`; summary.json carries per
generator `cache` (hit rate over fresh calls, cost split); `cache_watch.json` the PrefixWatch summary. The budget wrapper hosts the
circuit breaker (three consecutive zero-read calls on a written prefix stop the run) and, in the split layout, the run-level rule
(a fresh call whose prefix is not the one registered at the start raises before it is sent). Calls stay sequential.

Phase 2b additions (requirements.yaml `vendor_only_traces`, `evidence_vocabulary`): per sample `allows_vendor_only` (the
primary outcome of the evidence-vocabulary gate: allows a contract-deny trace whose only evidence is the vendor's) and
`evidence_text` (pgi.analysis.dogwood_text.vocabulary_report: which action each temporal predicate binds, each literal as
contract / vendor-stated / neither, approver-kind conjunct present; TEXT, labelled as such, never a decision). For the
Sondera-style generator `first_shot_valid` (round 1 passed strict validation) is reported next to post-repair validity.

Phase 2c additions (scenario.yaml `catalogue`, the trusted admission catalogue that names the protected action): per sample
`first_shot` (the round-1 text, which the naive and Sondera-style generators share through the cache: key hash, policy
sha256, validity, BIND, TOKEN) and `bind_token` on the final policy, both from pgi.analysis.dogwood_text.close_binding_report
(BIND = evidence roles of the temporal predicates in permits that can apply to the protected action; TOKEN = a
vendor-stated non-contract value in an authority predicate). TEXT, computed on every sample valid or not. `--input-mode`
is recorded in config.json and is part of the cache key through the system blocks.

E0 additions (requirements.yaml `workflows`, 2026-11-20): per scored sample `workflows_allowed` (the workflows whose every
trace the policy allows, i.e. whose positive tests it passes); summary `workflow_counts`. The class report that crosses
surplus with workflows is pgi.runs.workflow_classes (zero API, over run folders).

Scoring frame (`frame`): the suite (traces.yaml), gold's allow-set over it (checked against the contract before anything is
scored), and the requirement witnesses (requirements.yaml). Per sample: validity under the action + event schemas; the
decision of every trace; surplus = allowed minus gold, deficit = gold minus allowed. A replay error on a trace is recorded,
never read as a deny: the sample is `scored: false` and excluded from the rates. Requirement reconstruction: a scored
sample that allows the base trace reconstructs requirement R iff it denies every witness of R. All behaviour, never text.

Layout: runs/<id>/config.json, summary.json, summary.md, inputs/<scenario>/ (snapshot; generation and scoring read
only from it), <scenario>/prompt_static.json, and per generator/sample: response.json (or round<k>.json), policy.dw,
oracle.json. Samples run sequentially (the prompt cache must be readable). Same atomic folder and never-overwrite
rules as pgi.runs.clean, whose helpers this module reuses.
"""

from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import hashlib

from pgi.analysis.admission import load_catalogue
from pgi.analysis.dogwood_text import close_binding_report, vocabulary_report
from pgi.generators import dogwood
from pgi.generators.dogwood_inputs import DogwoodInputs, Requirements, load_dogwood_inputs, load_requirements, snapshot
from pgi.llm.cache import CachedLLM
from pgi.llm.deadline import DEFAULT_DEADLINE_S, CallDeadlineExceeded, DeadlineProvider
from pgi.llm.prefix import prefix_hash
from pgi.llm.pricing import cost
from pgi.runs.attempts import DEFAULT_MAX_RETRIES, DeadlineRunStopped, run_sample_with_retries
from pgi.runs.cache_watch import PrefixWatch, assumed_call_cost, cost_split, plan, plan_text
from pgi.oracle import temporal
from pgi.oracle.errors import OracleError
from pgi.runs.clean import _call_record, _dump, _NoProvider, atomic_run_dir, wilson

ROOT = Path(__file__).resolve().parents[3]
GENERATORS = ("naive", "sondera")


class SpendCapExceeded(RuntimeError):
    """The next API call would be made after the spend cap was reached; the run stops (samples so far are cached)."""


class _Budget:
    """Provider wrapper: adds up the cost of every fresh call from the API's usage fields and refuses a call once the cap
    is reached (`cap_usd` None = no cap). Cached hits never reach it. The first call always goes through (the cap is
    checked before each call). With a `watch` (PrefixWatch) it also runs the prompt-cache checks: the registered-prefix
    rule and the in-flight guard before the call, the circuit breaker after it, reading the cache counts through the
    provider's `cache_usage`; a provider without it disables the watch with a logged reason. A call that hits the wall-clock
    deadline (CallDeadlineExceeded from the DeadlineProvider underneath) is charged its worst case as `assumed_usd` (it may still
    be billed), marks the watch as expired (neither hit nor miss, guard released) and re-raises; `spent_usd` = observed + assumed."""

    def __init__(self, provider, model: str, cap_usd: float | None = None, watch: PrefixWatch | None = None) -> None:
        self.provider, self.model, self.cap_usd, self.spent_usd, self.calls = provider, model, cap_usd, 0.0, 0
        self.observed_usd, self.assumed_usd, self.expiries = 0.0, 0.0, 0
        self.watch, self.name = watch, provider.name
        if watch is not None and getattr(provider, "cache_usage", None) is None:
            watch.disable(f"provider {provider.name} reports no cache usage fields (no cache_usage method)")

    def call(self, model, messages, temperature, params):
        if self.cap_usd is not None and self.spent_usd >= self.cap_usd:
            raise SpendCapExceeded(f"spend cap ${self.cap_usd:.2f} reached (${self.spent_usd:.4f} over {self.calls} calls); refusing call {self.calls + 1}")
        h = prefix_hash(model, params, strict=False) if self.watch is not None else None
        if h is not None:
            self.watch.before(h)
        try:
            raw = self.provider.call(model, messages, temperature, params)
        except CallDeadlineExceeded as e:
            assumed = assumed_call_cost(model, messages, params)
            e.event["assumed_usd"], e.event["assumed_basis"] = assumed["usd"], assumed["basis"]
            self.expiries += 1
            self.assumed_usd += assumed["usd"]
            self.spent_usd += assumed["usd"]
            if h is not None:
                self.watch.expired(h)
            raise
        except BaseException:
            if h is not None:
                self.watch.abort(h)
            raise
        self.calls += 1
        observed = cost(model, self.provider.usage(raw) or {})
        self.observed_usd += observed
        self.spent_usd += observed
        if h is not None:
            cache_usage = getattr(self.provider, "cache_usage", None)
            cu = cache_usage(raw) if cache_usage is not None else None
            if cu is None:
                self.watch.disable(f"provider {self.provider.name} reports no cache usage fields")
            self.watch.after(h, cu)
        return raw

    def text(self, raw):
        return self.provider.text(raw)

    def model_version(self, raw):
        return self.provider.model_version(raw)

    def usage(self, raw):
        return self.provider.usage(raw)

    def spend(self) -> dict:
        """What the run records about money: observed from usage fields, assumed for abandoned calls, and their sum (the cap's view)."""
        return {"spent_usd": self.spent_usd, "observed_usd": self.observed_usd, "assumed_usd": self.assumed_usd, "calls": self.calls,
                "expiries": self.expiries}


@dataclass(frozen=True)
class Frame:
    """Everything a score depends on besides the policy."""

    inputs: DogwoodInputs
    suite: temporal.TraceSuite
    gold_allowed: frozenset[str]
    requirements: Requirements | None
    catalogue: dict | None = None

    @property
    def protected_action(self) -> str | None:
        return self.catalogue["protected_action"] if self.catalogue else None


def frame(inputs: DogwoodInputs) -> Frame:
    """Load the suite, the requirements and the catalogue; gold must equal the contract on every trace."""
    suite = temporal.load_suite(inputs.traces_yaml)
    gold = frozenset(temporal.allowed(inputs.gold, suite, inputs.schema_path, inputs.event_schema_path))
    if mismatch := sorted(t for t, want in suite.contract.items() if (t in gold) != want):
        raise OracleError(f"gold {inputs.gold} disagrees with the contract on {mismatch}; nothing scored")
    reqs = load_requirements(inputs.requirements, suite) if inputs.requirements else None
    cat = load_catalogue(inputs.catalogue) if inputs.catalogue else None
    return Frame(inputs, suite, gold, reqs, cat)


def bind_token(text: str, fr: Frame) -> dict | None:
    """Close-scoped BIND / TOKEN of one policy text, or None when the scenario has no catalogue or no vocabulary. TEXT."""
    if not (fr.protected_action and fr.requirements and fr.requirements.vocabulary):
        return None
    return close_binding_report(text, fr.requirements.vocabulary, fr.protected_action, fr.inputs.schema_text) | {
        "note": "text classification over permits that can apply to the protected action, not a decision"}


def _first_shot(text: str, key_hash: str, valid: bool, fr: Frame) -> dict:
    """What is recorded about a sample's first shot (round 1 = the naive request): identity, validity, BIND, TOKEN."""
    bt = bind_token(text, fr)
    return {"key_hash": key_hash, "policy_sha256": hashlib.sha256(text.encode()).hexdigest(), "valid": valid,
            "bind": bt["bind"] if bt else None, "token": bt["token"] if bt else None}


def _policy_file_text(policy_text: str) -> str:
    return policy_text + "\n" if policy_text else ""


def score(policy: Path, fr: Frame) -> dict:
    """The oracle record for one policy file (see module doc)."""
    inp = fr.inputs
    report = temporal.check(policy, inp.schema_path, inp.event_schema_path)
    out: dict = {"validation": report.as_dict(), "valid": report.ok}
    if report.ok and not dogwood.has_policy(Path(policy).read_text()):
        out["validation"]["errors"] = ["empty policy set: no permit or forbid policy found"]
        out["validation"]["ok"] = out["valid"] = False
    if (bt := bind_token(Path(policy).read_text(), fr)) is not None:
        out["bind_token"] = bt           # text; on every sample, valid or not
    if not out["valid"]:
        return out
    decisions, errors, prerequisite = {}, {}, None
    reqs = fr.requirements
    for tid, trace in fr.suite.traces.items():
        try:
            verdicts = temporal.replay(policy, inp.schema_path, trace, inp.event_schema_path)
            if not verdicts:
                raise OracleError(f"{trace}: no decision event, nothing to score")
        except OracleError as e:
            errors[tid] = str(e)
            continue
        decisions[tid] = verdicts[-1].allowed
        if reqs and reqs.prerequisite and reqs.prerequisite[0] == tid:
            prerequisite = verdicts[reqs.prerequisite[1]].allowed
    allowed = sorted(t for t, a in decisions.items() if a)
    out |= {"decisions": decisions, "replay_errors": errors, "scored": not errors, "allow_set": allowed}
    if not errors:
        out["surplus"], out["deficit"] = sorted(set(allowed) - fr.gold_allowed), sorted(fr.gold_allowed - set(allowed))
        if reqs:
            out["over_permissive"] = [t for t in reqs.over_permissive_if_allows if t in allowed]
            out["over_strict"] = [t for t in reqs.over_strict_if_denies if t not in allowed]
            out["sources_accepted"] = [name for name, t in (reqs.sources or {}).items() if t in allowed]
            out["prerequisite_permitted"] = prerequisite
            if reqs.vendor_only:
                out["allows_vendor_only"] = [t for t in reqs.vendor_only if t in allowed]
            if reqs.workflows:
                out["workflows_allowed"] = [w for w, ts in reqs.workflows.items() if set(ts) <= set(allowed)]
    if reqs and reqs.vocabulary:
        out["evidence_text"] = vocabulary_report(Path(policy).read_text(), reqs.vocabulary) | {"note": "text classification, not a decision"}
    return out


def _record(c, model: str, deadline_s: float | None = None, expiries_before: int = 0) -> dict:
    """A call record with the Phase 3 cache telemetry (prefix hash from the completion, cost split of its usage) and the
    deadline: the seconds in force (None in a cache-only run) and how many attempts on this sample expired before this call."""
    return _call_record(c) | {"cache_split": cost_split(model, c.usage or {}), "deadline_s": deadline_s, "expiries_before": expiries_before}


def run_naive(llm: CachedLLM, fr: Frame, cfg: dogwood.NaiveDogwoodConfig, i: int, d: Path, deadline_s: float | None = None,
              expiries_before: int = 0) -> dict:
    """One naive sample: generate, write, score."""
    s = dogwood.generate(llm, fr.inputs, cfg, i)
    d.mkdir(parents=True, exist_ok=True)
    (d / "policy.dw").write_text(_policy_file_text(s.policy_text))
    rec = _record(s.completion, cfg.model, deadline_s, expiries_before)
    _dump(d / "response.json", rec | {"extraction": s.extraction})
    oracle = score(d / "policy.dw", fr)
    _dump(d / "oracle.json", oracle)
    return {"sample": i, "calls": [rec], "oracle": oracle,
            "first_shot": _first_shot(_policy_file_text(s.policy_text), s.completion.key_hash, oracle["valid"], fr)}


def run_sondera(llm: CachedLLM, fr: Frame, cfg: dogwood.SonderaDogwoodConfig, i: int, d: Path, deadline_s: float | None = None,
                expiries_before: int = 0) -> dict:
    """One Sondera-style sample: up to max_rounds of generate + critics, then score the final policy."""
    res = dogwood.run(llm, fr.inputs, cfg, i, d)
    calls = []
    for r in res.rounds:
        rec = {"round": r.index, "extraction": r.extraction, "generation": _record(r.completion, cfg.model, deadline_s, expiries_before),
               "deterministic": r.deterministic.as_dict(), "judge": _record(r.judge_completion, cfg.model, deadline_s, expiries_before),
               "judge_passed": r.judge_passed, "passed": r.passed}
        _dump(d / f"round{r.index}.json", rec)
        calls += [rec["generation"], rec["judge"]]
    (d / "policy.dw").write_text(_policy_file_text(res.final_policy))
    oracle = score(d / "policy.dw", fr)
    r1 = res.rounds[0]
    crit = {"passed": res.passed, "rounds_used": res.rounds_used, "round1_valid": r1.deterministic.passed}
    first = _first_shot(_policy_file_text(r1.policy_text), r1.completion.key_hash,
                        r1.deterministic.validation.ok and dogwood.has_policy(r1.policy_text), fr)
    _dump(d / "oracle.json", oracle | {"critic": crit, "first_shot": first})
    return {"sample": i, "calls": calls, "oracle": oracle, "critic": crit, "first_shot": first}


def summarize(model: str, results: list[dict], fr: Frame) -> dict:
    """Per generator: validity, exactness, surplus/deficit, per-trace allow counts, requirement reconstruction, cost."""
    n = len(results)
    valid = [r for r in results if r["oracle"]["valid"]]
    scored = [r for r in valid if r["oracle"]["scored"]]
    ns = len(scored)
    allow = lambda r: set(r["oracle"]["allow_set"])
    exact = [r for r in scored if allow(r) == fr.gold_allowed]
    sur = [r for r in scored if r["oracle"]["surplus"]]
    dfc = [r for r in scored if r["oracle"]["deficit"]]
    calls = [c for r in results for c in r["calls"]]
    fresh = [c for c in calls if not c["cache_hit"]]
    share = lambda k, m: round(k / m, 3) if m else None
    out = {
        "n": n, "valid": len(valid), "validity_rate": share(len(valid), n), "validity_ci95": wilson(len(valid), n),
        "scored": ns, "replay_error_samples": [r["sample"] for r in valid if not r["oracle"]["scored"]],
        "replay_error_messages": dict(Counter(e.split(": ", 1)[-1][:160] for r in valid for e in r["oracle"]["replay_errors"].values())),
        "exact": len(exact), "exact_share_of_scored": share(len(exact), ns), "exact_ci95": wilson(len(exact), ns),
        "nonempty_surplus": len(sur), "nonempty_surplus_share_of_scored": share(len(sur), ns), "nonempty_surplus_ci95": wilson(len(sur), ns),
        "nonempty_deficit": len(dfc), "nonempty_deficit_share_of_scored": share(len(dfc), ns), "nonempty_deficit_ci95": wilson(len(dfc), ns),
        "surplus_trace_counts": dict(sorted(Counter(t for r in scored for t in r["oracle"]["surplus"]).items())),
        "deficit_trace_counts": dict(sorted(Counter(t for r in scored for t in r["oracle"]["deficit"]).items())),
        "clean_envelope": sorted(set().union(*(allow(r) for r in scored)) if scored else set()),
        "gold_allow_set": sorted(fr.gold_allowed),
        "allow_counts": {t: {"contract": fr.suite.contract[t], "gold": t in fr.gold_allowed,
                             "k": (k := sum(t in allow(r) for r in scored)), "n": ns, "ci95": wilson(k, ns)}
                         for t in fr.suite.traces},
        "stop_reasons": dict(sorted(Counter(str(c["stop_reason"]) for c in calls).items())),
        "model_versions": sorted({c["model_version"] for c in calls}),
        "calls": len(calls), "api_calls": len(fresh),
        "usage": {k: sum((c["usage"] or {}).get(k, 0) or 0 for c in calls)
                  for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")},
        "cost_usd_all_calls": round(sum(cost(model, c["usage"] or {}) for c in calls), 4),
        "cost_usd_this_run": round(sum(cost(model, c["usage"] or {}) for c in fresh), 4),
        # deadline expiries (abandoned calls, retried with the same request); the samples kept after a successful retry
        "deadline_expiries": sum(len(r.get("deadline_expiries") or []) for r in results),
        "samples_retried_after_expiry": [r["sample"] for r in results if r.get("deadline_expiries")],
        # Phase 3 prompt-cache telemetry over this run's fresh calls: hit = cache_read_input_tokens > 0
        "cache": {"hit_rate": {"k": sum(1 for c in fresh if ((c["usage"] or {}).get("cache_read_input_tokens") or 0) > 0), "n": len(fresh)},
                  "cost_split": cost_split(model, {k: sum(((c["usage"] or {}).get(k) or 0) for c in fresh)
                                                   for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}),
                  "prefix_hashes": sorted({c["prefix_hash"] for c in calls if c.get("prefix_hash")})},
    }
    if fr.requirements:
        base = fr.requirements.base
        functional = [r for r in scored if base in allow(r)]
        nf = len(functional)
        out["base_trace"] = base
        out["functional"] = nf
        out["functional_ci95"] = wilson(nf, ns)
        out["requirements"] = {}
        for name, witnesses in fr.requirements.witnesses.items():
            k = sum(not (set(witnesses) & allow(r)) for r in functional)
            out["requirements"][name] = {"requirement": fr.requirements.numbers[name], "witnesses": list(witnesses),
                                         "k": k, "n": nf, "share": share(k, nf), "ci95": wilson(k, nf)}
        out["all_requirements"] = sum(
            all(not (set(w) & allow(r)) for w in fr.requirements.witnesses.values()) for r in functional)
        reqs = fr.requirements
        over_p = [r for r in scored if r["oracle"]["over_permissive"]]
        over_s = [r for r in scored if r["oracle"]["over_strict"]]
        out["over_permissive"], out["over_permissive_ci95"] = len(over_p), wilson(len(over_p), ns)
        out["over_permissive_trace_counts"] = {t: sum(t in r["oracle"]["over_permissive"] for r in scored) for t in reqs.over_permissive_if_allows}
        out["over_strict"], out["over_strict_ci95"] = len(over_s), wilson(len(over_s), ns)
        out["over_strict_trace_counts"] = {t: sum(t in r["oracle"]["over_strict"] for r in scored) for t in reqs.over_strict_if_denies}
        out["sources_accepted_counts"] = {name: sum(name in r["oracle"]["sources_accepted"] for r in scored) for name in (reqs.sources or {})}
        out["sources_trace"] = dict(reqs.sources or {})
        out["source_sets"] = dict(Counter("+".join(r["oracle"]["sources_accepted"]) or "(none)" for r in scored))
        out["prerequisite_permitted"] = sum(bool(r["oracle"].get("prerequisite_permitted")) for r in scored)
        if reqs.vendor_only:  # Phase 2b primary outcome
            k = sum(bool(r["oracle"]["allows_vendor_only"]) for r in scored)
            out["allows_vendor_only"], out["allows_vendor_only_ci95"] = k, wilson(k, ns)
            out["vendor_only_traces"] = list(reqs.vendor_only)
            out["vendor_only_trace_counts"] = {t: sum(t in r["oracle"]["allows_vendor_only"] for r in scored) for t in reqs.vendor_only}
        if reqs.workflows:    # E0: positive tests per workflow
            out["workflow_counts"] = {w: {"traces": list(ts), "k": sum(w in r["oracle"]["workflows_allowed"] for r in scored), "n": ns}
                                      for w, ts in reqs.workflows.items()}
        if reqs.vocabulary:   # Phase 2b secondary outcomes (text)
            ev = [r["oracle"]["evidence_text"] for r in valid]
            out["evidence_text_n"] = len(ev)
            out["binding_counts"] = dict(sorted(Counter(e["binding"] for e in ev).items()))
            out["actions_bound_counts"] = dict(sorted(Counter(a for e in ev for a in e["actions_bound"]).items()))
            out["vendor_token_in_authority_predicate"] = sum(e["vendor_token_in_authority_predicate"] for e in ev)
            out["invented_in_authority_predicate"] = sum(e["invented_in_authority_predicate"] for e in ev)
            out["approver_kind_present"] = sum(e["approver_kind_present"] for e in ev)
            out["authority_literal_counts"] = {c: dict(sorted(Counter(v for e in ev for v in e["authority_literals"][c]).items()))
                                               for c in ("contract", "vendor_stated", "neither")}
    if fs := [r["first_shot"] for r in results if r.get("first_shot") and r["first_shot"].get("bind")]:   # Phase 2c, TEXT, all samples
        out["first_shot_bind_counts"] = dict(sorted(Counter(f["bind"] for f in fs).items()))
        out["first_shot_token"] = sum(bool(f["token"]) for f in fs)
    if bt := [r["oracle"]["bind_token"] for r in results if "bind_token" in r["oracle"]]:
        out["final_bind_counts"] = dict(sorted(Counter(b["bind"] for b in bt).items()))
        out["final_token"] = sum(bool(b["token"]) for b in bt)
        out["final_unresolved_scope"] = sum(bool(b["unresolved_scope"]) for b in bt)
    out["post_repair_valid"] = len(valid)
    if any("critic" in r for r in results):
        rounds = [r["critic"]["rounds_used"] for r in results]
        passed = [r for r in results if r["critic"]["passed"]]
        out["critic_passed"] = len(passed)
        out["critic_pass_ci95"] = wilson(len(passed), n)
        out["critic_passed_round1"] = sum(r["critic"]["rounds_used"] == 1 for r in passed)
        out["rounds_used_counts"] = {k: rounds.count(k) for k in sorted(set(rounds))}
        out["first_shot_valid"] = sum(bool(r["critic"].get("round1_valid")) for r in results)
        out["first_shot_valid_ci95"] = wilson(out["first_shot_valid"], n)
    else:
        out["first_shot_valid"], out["first_shot_valid_ci95"] = len(valid), wilson(len(valid), n)
    return out


def markdown(config: dict, summary: dict) -> str:
    """Human summary."""
    gens = list(summary)
    lines = [f"# Temporal clean run {config['run_id']}", "",
             f"Scenario `{config['scenario']}`, intent arm `{config.get('intent', {}).get('arm', '?')}`, manifest arm "
             f"`{config.get('arm', {}).get('name', 'base')}`, input mode `{config.get('input_mode', 'manifests')}`; model `{config['model']}` (API reported: "
             f"{', '.join(sorted({v for s in summary.values() for v in s['model_versions']}))}); N={config['n']}; "
             f"generators: {', '.join(gens)}. Oracle: Dogwood interpreter {config['versions']['dogwood']} via pydogwood "
             f"{config['versions']['pydogwood']}, replay over the {len(next(iter(summary.values()))['allow_counts'])}-trace suite "
             f"under the AWS-shaped event schema. Surrogate evidence about the pattern, not about AgentCore.", "",
             "| generator | valid | scored (no replay error) | exact = gold (of scored) | surplus≠∅ (of scored) | deficit≠∅ (of scored) | rounds | cost (all calls) |",
             "|---|---|---|---|---|---|---|---|"]
    for g, s in summary.items():
        lines.append(f"| {g} | {s['valid']}/{s['n']} {s['validity_ci95']} | {s['scored']}/{s['valid']} | {s['exact']}/{s['scored']} {s['exact_ci95']} "
                     f"| {s['nonempty_surplus']}/{s['scored']} {s['nonempty_surplus_ci95']} | {s['nonempty_deficit']}/{s['scored']} {s['nonempty_deficit_ci95']} "
                     f"| {s.get('rounds_used_counts', '—')} | ${s['cost_usd_all_calls']:.3f} |")
    lines += ["", "Intervals: 95% Wilson. Surplus/deficit: allow-set over the trace suite vs gold (= the contract)."]
    first = summary[gens[0]]
    lines += ["", "## Allow counts per trace", "", "| trace | contract | " + " | ".join(gens) + " |", "|---|---|" + "---|" * len(gens)]
    for t, row in first["allow_counts"].items():
        cells = [f"{summary[g]['allow_counts'][t]['k']}/{summary[g]['allow_counts'][t]['n']}" for g in gens]
        lines.append(f"| {t} | {'ALLOW' if row['contract'] else 'deny'} | " + " | ".join(cells) + " |")
    lines += ["", "k/n = scored samples allowing the trace / scored samples."]
    if "requirements" in first:
        lines += ["", "## Requirement reconstruction (functional samples: scored and allowing the base trace)", "",
                  "| requirement | # | witnesses | " + " | ".join(gens) + " |", "|---|---|---|" + "---|" * len(gens)]
        for name, row in first["requirements"].items():
            cells = [f"{summary[g]['requirements'][name]['k']}/{summary[g]['requirements'][name]['n']} {summary[g]['requirements'][name]['ci95']}" for g in gens]
            lines.append(f"| {name} | {row['requirement']} | {', '.join(row['witnesses'])} | " + " | ".join(cells) + " |")
        cells = [f"{summary[g]['all_requirements']}/{summary[g]['functional']}" for g in gens]
        lines.append("| **all** | | | " + " | ".join(cells) + " |")
        lines += ["", f"Functional: " + ", ".join(f"{g} {summary[g]['functional']}/{summary[g]['scored']}" for g in gens)
                  + f" (allow `{first['base_trace']}`). A requirement is reconstructed when every one of its witness traces is denied."]
    if "over_permissive" in first:
        op = "allows " + " / ".join(t.split("_")[0] for t in first["over_permissive_trace_counts"])
        os_ = "denies " + " / ".join(t.split("_")[0] for t in first["over_strict_trace_counts"])
        lines += ["", "## Security witnesses (scored samples)", "",
                  "| | " + " | ".join(gens) + " |", "|---|" + "---|" * len(gens),
                  f"| over-permissive: {op} | " + " | ".join(f"{summary[g]['over_permissive']}/{summary[g]['scored']} {summary[g]['over_permissive_ci95']}" for g in gens) + " |",
                  f"| over-strict: {os_} | " + " | ".join(f"{summary[g]['over_strict']}/{summary[g]['scored']} {summary[g]['over_strict_ci95']}" for g in gens) + " |",
                  "| evidence call permitted (t07 @100) | " + " | ".join(f"{summary[g]['prerequisite_permitted']}/{summary[g]['scored']}" for g in gens) + " |"]
        if "allows_vendor_only" in first:
            lines.append(f"| **allows a vendor-only trace (primary): {' / '.join(first['vendor_only_traces'])}** | "
                         + " | ".join(f"{summary[g]['allows_vendor_only']}/{summary[g]['scored']} {summary[g]['allows_vendor_only_ci95']}" for g in gens) + " |")
            lines.append("| per vendor-only trace | " + " | ".join(", ".join(f"{t.split('_')[0]} {k}" for t, k in summary[g]["vendor_only_trace_counts"].items()) for g in gens) + " |")
        lines += ["", "### Evidence source accepted (allows the single-source trace)", "",
                  "| source | trace | " + " | ".join(gens) + " |", "|---|---|" + "---|" * len(gens)]
        for name in first["sources_accepted_counts"]:
            lines.append(f"| {name} | {first['sources_trace'][name]} | " + " | ".join(f"{summary[g]['sources_accepted_counts'][name]}/{summary[g]['scored']}" for g in gens) + " |")
        lines += ["", "Source sets per sample: " + "; ".join(f"{g}: {summary[g]['source_sets']}" for g in gens) + "."]
    if "workflow_counts" in first:
        lines += ["", "## Workflows (scored samples passing every positive test of the workflow)", "",
                  "| workflow | traces | " + " | ".join(gens) + " |", "|---|---|" + "---|" * len(gens)]
        for w, row in first["workflow_counts"].items():
            lines.append(f"| {w} | {', '.join(row['traces'])} | " + " | ".join(f"{summary[g]['workflow_counts'][w]['k']}/{summary[g]['workflow_counts'][w]['n']}" for g in gens) + " |")
    if "binding_counts" in first:
        lines += ["", "## Evidence vocabulary (TEXT tally of temporal predicates over valid samples; explanatory, not a decision)", "",
                  "| | " + " | ".join(gens) + " |", "|---|" + "---|" * len(gens),
                  "| evidence action bound (binding → samples) | " + " | ".join(str(summary[g]["binding_counts"]) for g in gens) + " |",
                  "| vendor token in an authority predicate (vendor-stated, not contract) | " + " | ".join(f"{summary[g]['vendor_token_in_authority_predicate']}/{summary[g]['evidence_text_n']}" for g in gens) + " |",
                  "| invented literal in an authority predicate (neither) | " + " | ".join(f"{summary[g]['invented_in_authority_predicate']}/{summary[g]['evidence_text_n']}" for g in gens) + " |",
                  "| approver-kind conjunct present | " + " | ".join(f"{summary[g]['approver_kind_present']}/{summary[g]['evidence_text_n']}" for g in gens) + " |",
                  "| authority-predicate literals by class | " + " | ".join(str(summary[g]["authority_literal_counts"]) for g in gens) + " |"]
    if "final_bind_counts" in first:
        lines += ["", "## BIND / TOKEN (TEXT; permits that can apply to the protected action; all samples, valid or not)", "",
                  "| | " + " | ".join(gens) + " |", "|---|" + "---|" * len(gens),
                  "| first shot BIND (bind → samples) | " + " | ".join(str(summary[g].get("first_shot_bind_counts", "—")) for g in gens) + " |",
                  "| first shot TOKEN | " + " | ".join(f"{summary[g]['first_shot_token']}/{summary[g]['n']}" if "first_shot_token" in summary[g] else "—" for g in gens) + " |",
                  "| final BIND | " + " | ".join(str(summary[g]["final_bind_counts"]) for g in gens) + " |",
                  "| final TOKEN | " + " | ".join(f"{summary[g]['final_token']}/{summary[g]['n']}" for g in gens) + " |",
                  "| final: permits with unresolved scope | " + " | ".join(str(summary[g]["final_unresolved_scope"]) for g in gens) + " |"]
        if any("first_shot_shared_with_naive" in summary[g] for g in gens):
            lines.append("| first shot shared with naive (same cache entry) | " + " | ".join(
                f"{summary[g]['first_shot_shared_with_naive']['k']}/{summary[g]['first_shot_shared_with_naive']['n']}" if "first_shot_shared_with_naive" in summary[g] else "—" for g in gens) + " |")
        lines += ["", "BIND: authority / vendor / both / none over the temporal predicates of permits scoped to the protected action "
                      "(TOKEN: a vendor-stated, non-contract value in an authority predicate anywhere in the policy). The first shot is "
                      "round 1 of the Sondera-style loop, which is the naive request; the two generators share it, so first-shot and "
                      "final columns are two views of 20 samples, not 40."]
    lines += ["", "## Prompt cache (fresh calls of this run; hit = cache_read_input_tokens > 0)", "",
              "| generator | fresh calls | cache hits | cache write $ | cache read $ | uncached input $ | output $ | total $ | prefix hashes |", "|---|---|---|---|---|---|---|---|---|"]
    for g, s in summary.items():
        c = s["cache"]
        usd = c["cost_split"]["usd"]
        lines.append(f"| {g} | {c['hit_rate']['n']} | {c['hit_rate']['k']}/{c['hit_rate']['n']} | {usd['cache_write']:.3f} | {usd['cache_read']:.3f} "
                     f"| {usd['uncached_input']:.3f} | {usd['output']:.3f} | {c['cost_split']['total_usd']:.3f} | {', '.join(h[:12] for h in c['prefix_hashes'])} |")
    dl = config.get("request", {}).get("deadline") or {}
    lines += ["", f"## Deadline ({dl.get('seconds')} s per call, {dl.get('retries_on_expiry')} retries on expiry)", "",
              "| generator | expiry events | samples retried after an expiry |", "|---|---|---|"]
    for g, s in summary.items():
        lines.append(f"| {g} | {s.get('deadline_expiries', 0)} | {len(s.get('samples_retried_after_expiry') or [])} |")
    lines += ["", "An expired call is abandoned and never cached; the sample is retried with the same request (up to twice) and, if a retry "
                  "succeeds, kept as a normal sample. After the third expiry the run stops."]
    lines += ["", "## Validity: first-shot vs post-repair", "", "| generator | first-shot valid | post-repair (final) valid |", "|---|---|---|"]
    for g, s in summary.items():
        lines.append(f"| {g} | {s['first_shot_valid']}/{s['n']} {s['first_shot_valid_ci95']} | {s['post_repair_valid']}/{s['n']} {s['validity_ci95']} |")
    lines += ["", "first-shot = round 1 passed strict validation (naive has no repair loop, so both columns coincide)."]
    if any(s["replay_error_samples"] for s in summary.values()):
        lines += ["", "## Replay errors (recorded, not denies)", ""]
        for g, s in summary.items():
            if s["replay_error_samples"]:
                lines.append(f"- {g}: samples {s['replay_error_samples']}: " + "; ".join(f"`{m}` ×{k}" for m, k in s["replay_error_messages"].items()))
    crit = {g: s for g, s in summary.items() if "critic_passed" in s}
    if crit:
        lines += ["", "## Critic", "", "| generator | passed both critics | passed in round 1 | rounds used |", "|---|---|---|---|"]
        for g, s in crit.items():
            lines.append(f"| {g} | {s['critic_passed']}/{s['n']} {s['critic_pass_ci95']} | {s['critic_passed_round1']}/{s['n']} | {s['rounds_used_counts']} |")
    return "\n".join(lines) + "\n"


def _rel(p: Path | None) -> str | None:
    """A path relative to the repo root when it is under it (the normal case), else as given."""
    if p is None:
        return None
    p = Path(p)
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


def _versions() -> dict:
    def cmd(*a):
        try:
            return subprocess.run(list(a), capture_output=True, text=True).stdout.strip().splitlines()[0]
        except Exception as e:  # recorded, not fatal
            return f"unavailable: {e}"
    return {**temporal.tool_versions(), "anthropic": md.version("anthropic"),
            "git_commit": cmd("git", "-C", str(ROOT), "rev-parse", "HEAD"),
            "git_dirty": bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "src", "domains"],
                                             capture_output=True, text=True).stdout.strip())}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--model", required=True)
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--scenario", type=Path, required=True)
    p.add_argument("--label", default="")
    p.add_argument("--intent", help="intent arm named in scenario.yaml `intents` (default: the scenario's `intent` file)")
    p.add_argument("--arm", help="manifest arm named in scenario.yaml `arms` (default: the scenario's top-level files)")
    p.add_argument("--spend-cap-usd", type=float, help="refuse any API call once fresh calls of this run have cost this much")
    p.add_argument("--generators", nargs="+", default=list(GENERATORS), choices=GENERATORS)
    p.add_argument("--no-descriptions", action="store_true", help="include_descriptions=False")
    p.add_argument("--input-mode", default="manifests", choices=dogwood.INPUT_MODES,
                   help="what the generator sees besides the intent: manifests (default; schema + event schema + raw manifests) or schema-only")
    p.add_argument("--judge-sees-manifests", action="store_true")
    p.add_argument("--cache-only", action="store_true", help="every LLM call must hit the cache; zero API calls")
    p.add_argument("--cache", type=Path, default=ROOT / "cache/llm")
    p.add_argument("--layout", default="default", choices=dogwood.LAYOUTS,
                   help="prompt layout: default (breakpoint on the last static block) or split (Phase 3: fixed blocks 1-4, breakpoint on the MaintData-only schema)")
    p.add_argument("--contract-block", action="store_true", help="Phase 3 D4: append the trusted evidence-authority contract (catalogue) as the last system block; split layout only")
    p.add_argument("--plan", action="store_true", help="no API call and no run folder: print call counts, prefix hashes, sizes and the expected cost")
    p.add_argument("--runs-dir", type=Path, default=ROOT / "runs", help="where run folders are written and, for --plan, where recorded token counts are looked up")
    p.add_argument("--deadline-s", type=float, default=DEFAULT_DEADLINE_S,
                   help="wall-clock deadline around every API call, enforced outside the SDK; an expired call is abandoned and the sample retried (default 600)")
    args = p.parse_args()
    ncfg = dogwood.NaiveDogwoodConfig(args.model, include_descriptions=not args.no_descriptions, input_mode=args.input_mode,
                                      layout=args.layout, contract_block=args.contract_block)
    scfg = dogwood.SonderaDogwoodConfig(args.model, include_descriptions=not args.no_descriptions,
                                        judge_sees_manifests=args.judge_sees_manifests, input_mode=args.input_mode,
                                        layout=args.layout, contract_block=args.contract_block)
    if args.plan:
        print(plan_text(plan(load_dogwood_inputs(args.scenario, args.intent, args.arm), ncfg, scfg, args.generators, args.n, args.runs_dir)))
        return
    from pgi.llm.anthropic_provider import AnthropicProvider
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = "-".join(x for x in (stamp, "temporal-clean", args.label) if x)
    with atomic_run_dir(args.runs_dir, run_id) as out:
        src_inputs = load_dogwood_inputs(args.scenario, args.intent, args.arm)
        inp = snapshot(src_inputs, out / "inputs" / args.scenario.name)
        fr = frame(inp)
        # Phase 3: the prefixes this run will use, computed before any call (judge only when the pipeline has one)
        prefixes = {"generation": prefix_hash(args.model, dogwood.build_request(inp, ncfg)[1]),
                    "judge": prefix_hash(args.model, dogwood.judge_request(inp, "", scfg)[1]) if "sondera" in args.generators else None}
        watch = None
        if args.cache_only:
            provider, transport = _NoProvider(), None
            telemetry = {"enabled": False, "reason": "cache-only run: no API call, nothing to observe"}
            rule = "off (cache-only run)"
        else:
            provider = DeadlineProvider(AnthropicProvider(), seconds=args.deadline_s)
            transport = provider.request_settings()
            rule = "on" if args.layout == "split" else "off (default layout)"
            watch = PrefixWatch(expected={k: v for k, v in prefixes.items() if v} if args.layout == "split" else None, model=args.model)
            provider = _Budget(provider, args.model, args.spend_cap_usd, watch)
            telemetry = {"enabled": watch.enabled, "reason": watch.disabled_reason}
        llm = CachedLLM(provider, args.cache, allow_api=not args.cache_only)
        config = {"run_id": run_id, "created": stamp, "kind": "temporal-clean", "model": args.model, "n": args.n,
                  "cache_only": args.cache_only, "scenario": inp.name,
                  "intent": {"arm": inp.intent_name, "file": src_inputs.intent_path.name, "sha256": inp.hashes["intent"]},
                  "arm": {"name": inp.arm_name,
                          "files": {"manifests": {s: _rel(p) for s, p in zip(src_inputs.servers, src_inputs.manifest_paths)},
                                    "schema": _rel(src_inputs.schema_path), "gold": _rel(src_inputs.gold),
                                    "traces": _rel(src_inputs.traces_yaml), "requirements": _rel(src_inputs.requirements),
                                    "prompt_schema_base": _rel(src_inputs.schema_base_path)}},
                  "spend_cap_usd": args.spend_cap_usd, "input_mode": args.input_mode,
                  "inputs": "inputs/<scenario>/ (snapshot; generation and scoring read only from it)",
                  "generators": {"naive": ncfg.as_dict(), "sondera": scfg.as_dict()}, "generators_run": args.generators,
                  "request": {"sampling": "not sent (API default)", "thinking": {"type": "adaptive"},
                              "output_config": {"effort": ncfg.effort}, "max_tokens": ncfg.max_tokens,
                              "fallbacks": "none",
                              "prompt_cache": {"layout": args.layout,
                                               "breakpoint": ("ephemeral breakpoint on the last static system block" if args.layout == "default" else
                                                              "ephemeral breakpoint on block 4 (action schema part 1 = prompt_schema_base); part 2 and the contract block after it"),
                                               "prefix_hashes": prefixes, "telemetry": telemetry, "run_level_prefix_rule": rule,
                                               "circuit_breaker": "3 consecutive zero-read fresh calls on a written prefix stop the run" if watch else None},
                              "transport": transport,
                              "deadline": {"seconds": args.deadline_s if not args.cache_only else None, "retries_on_expiry": DEFAULT_MAX_RETRIES,
                                           "rule": "a sample whose call expires is retried with the same request up to twice; after the third expiry the run stops; "
                                                   "a sample that succeeded after one or two expiries is a normal sample; a late result is never cached"}},
                  "frame": {"schema": str(inp.schema_path.relative_to(out)), "event_schema": str(inp.event_schema_path.relative_to(out)),
                            "traces": sorted(fr.suite.ids), "gold_allow_set": sorted(fr.gold_allowed),
                            "requirements": fr.requirements.witnesses if fr.requirements else None,
                            "vendor_only_traces": list(fr.requirements.vendor_only) if fr.requirements else None,
                            "evidence_vocabulary": fr.requirements.vocabulary if fr.requirements else None,
                            "catalogue": str(inp.catalogue.relative_to(out)) if inp.catalogue else None,
                            "protected_action": fr.protected_action},
                  "hashes": inp.hashes, "versions": _versions()}
        _dump(out / "config.json", config)
        _dump(out / inp.name / "prompt_static.json", dogwood.build_request(inp, ncfg)[1]["system"])
        results: dict[str, list[dict]] = {}
        deadline_s = None if args.cache_only else args.deadline_s
        events: list[dict] = []   # every expiry event of the run, in order
        try:
            for gen in args.generators:
                rows = []
                for i in range(args.n):
                    d = out / inp.name / gen / f"sample_{i:02d}"

                    def one(attempt: int, gen=gen, i=i, d=d) -> dict:
                        before = attempt - 1
                        return run_naive(llm, fr, ncfg, i, d, deadline_s, before) if gen == "naive" else run_sondera(llm, fr, scfg, i, d, deadline_s, before)
                    try:
                        row, ev = run_sample_with_retries(one, generator=gen, sample=i)
                    except DeadlineRunStopped as e:
                        events += e.events
                        raise
                    events += ev
                    row["deadline_expiries"] = ev
                    if ev:
                        _dump(d / "deadline.json", ev)
                        print(f"{gen} sample {i}: {len(ev)} call(s) expired at the {deadline_s:g} s deadline before a retry succeeded", flush=True)
                    rows.append(row)
                    o = row["oracle"]
                    print(f"{gen} sample {i}: valid={o['valid']} scored={o.get('scored')} surplus={o.get('surplus')} "
                          f"deficit={o.get('deficit')} replay_errors={len(o.get('replay_errors', {}))}", flush=True)
                results[gen] = rows
        finally:   # on a stop (or any failure) the events and the spend so far are still written next to FAILED
            _dump(out / "deadline_events.json", events)
            if isinstance(provider, _Budget):
                _dump(out / "spend.json", provider.spend() | {"cap_usd": provider.cap_usd, "assumed": "an abandoned call is charged its worst case (cache_watch.assumed_call_cost)"})
        summary = {g: summarize(args.model, results[g], fr) for g in results}
        if {"naive", "sondera"} <= set(results):   # A0: the first shot is one generation per sample, shared through the cache
            shared = sum(a["first_shot"]["key_hash"] == b["first_shot"]["key_hash"] and a["first_shot"]["policy_sha256"] == b["first_shot"]["policy_sha256"]
                         for a, b in zip(results["naive"], results["sondera"]))
            summary["sondera"]["first_shot_shared_with_naive"] = {"k": shared, "n": args.n}
        _dump(out / "summary.json", summary)
        (out / "summary.md").write_text(markdown(config, summary))
        if watch is not None:
            _dump(out / "cache_watch.json", watch.summary())
    spent = ""
    if isinstance(provider, _Budget):
        spent = f"; spent ${provider.spent_usd:.4f}" + (f" of cap ${provider.cap_usd:.2f}" if provider.cap_usd is not None else "")
        if provider.expiries:
            spent += f" (observed ${provider.observed_usd:.4f} + assumed ${provider.assumed_usd:.4f} for {provider.expiries} abandoned call(s))"
        if watch is not None and watch.enabled:
            hr = watch.summary()["hit_rate"]
            spent += f"; cache hits {hr['k']}/{hr['n']} fresh calls"
    print(f"\nwrote {args.runs_dir / run_id}\napi calls this run: {llm.api_calls}{spent}")


if __name__ == "__main__":
    main()
