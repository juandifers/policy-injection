"""Temporal clean runs: N Dogwood samples per generator for one temporal scenario, scored by pgi.oracle.temporal over the
scenario's trace suite, written to runs/<id>/.

    uv run --group dogwood python -m pgi.runs.temporal_clean --model claude-sonnet-5-5 --n 20 \
        --scenario domains/assetopsbench/scenarios/t01_close_after_approval --label t01
    ... --cache-only            # every LLM call must hit the cache (re-score; zero API calls)

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

from pgi.generators import dogwood
from pgi.generators.dogwood_inputs import DogwoodInputs, Requirements, load_dogwood_inputs, load_requirements, snapshot
from pgi.llm.cache import CachedLLM
from pgi.llm.pricing import cost
from pgi.oracle import temporal
from pgi.oracle.errors import OracleError
from pgi.runs.clean import _call_record, _dump, _NoProvider, atomic_run_dir, wilson

ROOT = Path(__file__).resolve().parents[3]
GENERATORS = ("naive", "sondera")


@dataclass(frozen=True)
class Frame:
    """Everything a score depends on besides the policy."""

    inputs: DogwoodInputs
    suite: temporal.TraceSuite
    gold_allowed: frozenset[str]
    requirements: Requirements | None


def frame(inputs: DogwoodInputs) -> Frame:
    """Load the suite and the requirements; gold must equal the contract on every trace."""
    suite = temporal.load_suite(inputs.traces_yaml)
    gold = frozenset(temporal.allowed(inputs.gold, suite, inputs.schema_path, inputs.event_schema_path))
    if mismatch := sorted(t for t, want in suite.contract.items() if (t in gold) != want):
        raise OracleError(f"gold {inputs.gold} disagrees with the contract on {mismatch}; nothing scored")
    reqs = load_requirements(inputs.requirements, suite) if inputs.requirements else None
    return Frame(inputs, suite, gold, reqs)


def score(policy: Path, fr: Frame) -> dict:
    """The oracle record for one policy file (see module doc)."""
    inp = fr.inputs
    report = temporal.check(policy, inp.schema_path, inp.event_schema_path)
    out: dict = {"validation": report.as_dict(), "valid": report.ok}
    if report.ok and not dogwood.has_policy(Path(policy).read_text()):
        out["validation"]["errors"] = ["empty policy set: no permit or forbid policy found"]
        out["validation"]["ok"] = out["valid"] = False
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
    return out


def run_naive(llm: CachedLLM, fr: Frame, cfg: dogwood.NaiveDogwoodConfig, i: int, d: Path) -> dict:
    """One naive sample: generate, write, score."""
    s = dogwood.generate(llm, fr.inputs, cfg, i)
    d.mkdir(parents=True, exist_ok=True)
    (d / "policy.dw").write_text(s.policy_text + "\n" if s.policy_text else "")
    _dump(d / "response.json", _call_record(s.completion) | {"extraction": s.extraction})
    oracle = score(d / "policy.dw", fr)
    _dump(d / "oracle.json", oracle)
    return {"sample": i, "calls": [_call_record(s.completion)], "oracle": oracle}


def run_sondera(llm: CachedLLM, fr: Frame, cfg: dogwood.SonderaDogwoodConfig, i: int, d: Path) -> dict:
    """One Sondera-style sample: up to max_rounds of generate + critics, then score the final policy."""
    res = dogwood.run(llm, fr.inputs, cfg, i, d)
    calls = []
    for r in res.rounds:
        rec = {"round": r.index, "extraction": r.extraction, "generation": _call_record(r.completion),
               "deterministic": r.deterministic.as_dict(), "judge": _call_record(r.judge_completion),
               "judge_passed": r.judge_passed, "passed": r.passed}
        _dump(d / f"round{r.index}.json", rec)
        calls += [rec["generation"], rec["judge"]]
    (d / "policy.dw").write_text(res.final_policy + "\n" if res.final_policy else "")
    oracle = score(d / "policy.dw", fr)
    crit = {"passed": res.passed, "rounds_used": res.rounds_used}
    _dump(d / "oracle.json", oracle | {"critic": crit})
    return {"sample": i, "calls": calls, "oracle": oracle, "critic": crit}


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
    if any("critic" in r for r in results):
        rounds = [r["critic"]["rounds_used"] for r in results]
        passed = [r for r in results if r["critic"]["passed"]]
        out["critic_passed"] = len(passed)
        out["critic_pass_ci95"] = wilson(len(passed), n)
        out["critic_passed_round1"] = sum(r["critic"]["rounds_used"] == 1 for r in passed)
        out["rounds_used_counts"] = {k: rounds.count(k) for k in sorted(set(rounds))}
    return out


def markdown(config: dict, summary: dict) -> str:
    """Human summary."""
    gens = list(summary)
    lines = [f"# Temporal clean run {config['run_id']}", "",
             f"Scenario `{config['scenario']}`, intent arm `{config.get('intent', {}).get('arm', '?')}`; model `{config['model']}` (API reported: "
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
        lines += ["", "## Security witnesses (scored samples)", "",
                  "| | " + " | ".join(gens) + " |", "|---|" + "---|" * len(gens),
                  "| over-permissive: allows t05 / t08 / t09 / t11 | " + " | ".join(f"{summary[g]['over_permissive']}/{summary[g]['scored']} {summary[g]['over_permissive_ci95']}" for g in gens) + " |",
                  "| over-strict: denies t01 / t12 / t13 | " + " | ".join(f"{summary[g]['over_strict']}/{summary[g]['scored']} {summary[g]['over_strict_ci95']}" for g in gens) + " |",
                  "| evidence call permitted (t07 @100) | " + " | ".join(f"{summary[g]['prerequisite_permitted']}/{summary[g]['scored']}" for g in gens) + " |"]
        lines += ["", "### Evidence source accepted (allows the single-source trace)", "",
                  "| source | trace | " + " | ".join(gens) + " |", "|---|---|" + "---|" * len(gens)]
        for name in first["sources_accepted_counts"]:
            lines.append(f"| {name} | {first['sources_trace'][name]} | " + " | ".join(f"{summary[g]['sources_accepted_counts'][name]}/{summary[g]['scored']}" for g in gens) + " |")
        lines += ["", "Source sets per sample: " + "; ".join(f"{g}: {summary[g]['source_sets']}" for g in gens) + "."]
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
    p.add_argument("--generators", nargs="+", default=list(GENERATORS), choices=GENERATORS)
    p.add_argument("--no-descriptions", action="store_true", help="include_descriptions=False")
    p.add_argument("--judge-sees-manifests", action="store_true")
    p.add_argument("--cache-only", action="store_true", help="every LLM call must hit the cache; zero API calls")
    p.add_argument("--cache", type=Path, default=ROOT / "cache/llm")
    args = p.parse_args()
    from pgi.llm.anthropic_provider import AnthropicProvider
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = "-".join(x for x in (stamp, "temporal-clean", args.label) if x)
    with atomic_run_dir(ROOT / "runs", run_id) as out:
        llm = CachedLLM(_NoProvider() if args.cache_only else AnthropicProvider(), args.cache, allow_api=not args.cache_only)
        ncfg = dogwood.NaiveDogwoodConfig(args.model, include_descriptions=not args.no_descriptions)
        scfg = dogwood.SonderaDogwoodConfig(args.model, include_descriptions=not args.no_descriptions,
                                            judge_sees_manifests=args.judge_sees_manifests)
        src_inputs = load_dogwood_inputs(args.scenario, args.intent)
        inp = snapshot(src_inputs, out / "inputs" / args.scenario.name)
        fr = frame(inp)
        config = {"run_id": run_id, "created": stamp, "kind": "temporal-clean", "model": args.model, "n": args.n,
                  "cache_only": args.cache_only, "scenario": inp.name,
                  "intent": {"arm": inp.intent_name, "file": src_inputs.intent_path.name, "sha256": inp.hashes["intent"]},
                  "inputs": "inputs/<scenario>/ (snapshot; generation and scoring read only from it)",
                  "generators": {"naive": ncfg.as_dict(), "sondera": scfg.as_dict()}, "generators_run": args.generators,
                  "request": {"sampling": "not sent (API default)", "thinking": {"type": "adaptive"},
                              "output_config": {"effort": ncfg.effort}, "max_tokens": ncfg.max_tokens,
                              "fallbacks": "none", "prompt_cache": "ephemeral breakpoint on last static system block"},
                  "frame": {"schema": str(inp.schema_path.relative_to(out)), "event_schema": str(inp.event_schema_path.relative_to(out)),
                            "traces": sorted(fr.suite.ids), "gold_allow_set": sorted(fr.gold_allowed),
                            "requirements": fr.requirements.witnesses if fr.requirements else None},
                  "hashes": inp.hashes, "versions": _versions()}
        _dump(out / "config.json", config)
        _dump(out / inp.name / "prompt_static.json", dogwood.build_request(inp, ncfg)[1]["system"])
        results: dict[str, list[dict]] = {}
        for gen in args.generators:
            rows = []
            for i in range(args.n):
                d = out / inp.name / gen / f"sample_{i:02d}"
                row = run_naive(llm, fr, ncfg, i, d) if gen == "naive" else run_sondera(llm, fr, scfg, i, d)
                rows.append(row)
                o = row["oracle"]
                print(f"{gen} sample {i}: valid={o['valid']} scored={o.get('scored')} surplus={o.get('surplus')} "
                      f"deficit={o.get('deficit')} replay_errors={len(o.get('replay_errors', {}))}", flush=True)
            results[gen] = rows
        summary = {g: summarize(args.model, results[g], fr) for g in results}
        _dump(out / "summary.json", summary)
        (out / "summary.md").write_text(markdown(config, summary))
    print(f"\nwrote {ROOT / 'runs' / run_id}\napi calls this run: {llm.api_calls}")


if __name__ == "__main__":
    main()
