"""Clean runs: N samples per scenario per generator, scored by the oracle, written to runs/<id>/.

    uv run python -m pgi.runs.clean --model claude-haiku-5-5 --n 2 --label smoke
    uv run python -m pgi.runs.clean --model claude-sonnet-5-5 --n 20 --replay   # cache only, zero API calls

Layout: runs/<id>/config.json, summary.json, summary.md, and per scenario/generator/sample:
response(s), policy.cedar, oracle.json. The static prompt prefix is stored once per scenario.
Samples within a scenario run sequentially (the prompt cache must be readable); scenarios run in parallel.
"""

from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import math
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from pgi.generators import critic, naive
from pgi.generators.inputs import ScenarioInputs, load_scenario_inputs
from pgi.llm.cache import CachedLLM, Completion
from pgi.llm.pricing import cost
from pgi.runs.judge import score

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCENARIOS = [ROOT / "domains/assetopsbench/scenarios" / s
                     for s in ("s01_close_after_approval", "s02_site_scoped_reads", "s03_create_at_main")]
GENERATORS = ("naive", "sondera")


def _dump(path: Path, obj) -> None:
    """Write JSON, creating parents; refuse to overwrite."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"{path} exists; runs are never overwritten")
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str) + "\n")


def _call_record(c: Completion) -> dict:
    """What we keep about one LLM call (the prompt lives in the cache entry and the scenario's prompt files)."""
    raw = c.raw
    return {"key_hash": c.key_hash, "cache_hit": c.cache_hit, "model_version": c.model_version,
            "request_id": raw.get("_request_id"), "stop_reason": raw.get("stop_reason"),
            "stop_details": raw.get("stop_details"), "usage": c.usage, "text": c.text,
            "content_types": [b.get("type") for b in raw.get("content", [])]}


def _tool_versions() -> dict:
    """Versions of everything that can change a result."""
    def cmd(*a):
        try:
            return subprocess.run(list(a), capture_output=True, text=True).stdout.strip().splitlines()[0]
        except Exception as e:  # recorded, not fatal
            return f"unavailable: {e}"
    import os
    return {"cedarpy": md.version("cedarpy"), "anthropic": md.version("anthropic"),
            "cedar-policy-mcp-schema-generator": md.version("cedar-policy-mcp-schema-generator"),
            "cedar_cli": cmd("cedar", "--version"), "cvc5": cmd(os.environ.get("CVC5", "cvc5"), "--version"),
            "git_commit": cmd("git", "-C", str(ROOT), "rev-parse", "HEAD"),
            "git_dirty": bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "src", "domains"],
                                             capture_output=True, text=True).stdout.strip())}


def run_naive(llm: CachedLLM, inp: ScenarioInputs, cfg: naive.NaiveConfig, i: int, d: Path) -> dict:
    """One naive sample: generate, write, score."""
    s = naive.generate(llm, inp, cfg, i)
    (d / "policy.cedar").parent.mkdir(parents=True, exist_ok=True)
    (d / "policy.cedar").write_text(s.policy_text + "\n" if s.policy_text else "")
    _dump(d / "response.json", _call_record(s.completion) | {"extraction": s.extraction})
    oracle = score(d / "policy.cedar", inp)
    _dump(d / "oracle.json", oracle)
    return {"sample": i, "calls": [_call_record(s.completion)], "oracle": oracle}


def run_sondera(llm: CachedLLM, inp: ScenarioInputs, cfg: critic.SonderaConfig, i: int, d: Path) -> dict:
    """One Sondera-style sample: up to max_rounds of generate + critics, then score the output."""
    res = critic.run(llm, inp, cfg, i, d)
    calls = []
    for r in res.rounds:
        rec = {"round": r.index, "extraction": r.extraction, "generation": _call_record(r.completion),
               "deterministic": r.deterministic.as_dict(), "judge": _call_record(r.judge_completion),
               "judge_passed": r.judge_passed, "passed": r.passed}
        _dump(d / f"round{r.index}.json", rec)
        calls += [rec["generation"], rec["judge"]]
    (d / "policy.cedar").write_text(res.final_policy + "\n" if res.final_policy else "")
    oracle = score(d / "policy.cedar", inp)
    _dump(d / "oracle.json", oracle | {"critic": {"passed": res.passed, "rounds_used": res.rounds_used}})
    return {"sample": i, "calls": calls, "oracle": oracle, "critic": {"passed": res.passed, "rounds_used": res.rounds_used}}


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """95% Wilson score interval for k successes in n trials."""
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def summarize(model: str, results: list[dict]) -> dict:
    """Per scenario x generator: validity, surplus/deficit shares, clean envelope, symcc, blind spots, cost."""
    n = len(results)
    valid = [r for r in results if r["oracle"]["valid"]]
    nv = len(valid)
    sur = [r for r in valid if r["oracle"]["enumeration"]["surplus"]]
    dfc = [r for r in valid if r["oracle"]["enumeration"]["deficit"]]
    sym_loose = [r for r in valid if not r["oracle"]["symbolic"]["implies_reference"]]
    freq = lambda key: dict(sorted({c: sum(c in r["oracle"]["enumeration"][key] for r in valid)
                                    for r in valid for c in r["oracle"]["enumeration"][key]}.items()))
    calls = [c for r in results for c in r["calls"]]
    fresh = [c for c in calls if not c["cache_hit"]]
    status = {}
    for r in valid:
        for row in r["oracle"]["symbolic"]["per_action"]:
            status[row["status"]] = status.get(row["status"], 0) + 1
    out = {
        "n": n, "valid": nv, "validity_rate": round(nv / n, 3) if n else None, "validity_ci95": wilson(nv, n),
        "nonempty_surplus": len(sur), "nonempty_surplus_share_of_valid": round(len(sur) / nv, 3) if nv else None,
        "nonempty_surplus_ci95": wilson(len(sur), nv),
        "nonempty_deficit": len(dfc), "nonempty_deficit_share_of_valid": round(len(dfc) / nv, 3) if nv else None,
        "nonempty_deficit_ci95": wilson(len(dfc), nv),
        "surplus_case_counts": freq("surplus"), "deficit_case_counts": freq("deficit"),
        "clean_envelope": sorted(set().union(*(set(r["oracle"]["enumeration"]["allow_set"]) for r in valid))),
        "symbolic_not_implies_reference": len(sym_loose), "symbolic_status_counts": status,
        "blind_spots": [{"sample": r["sample"], "actions": r["oracle"]["symbolic"]["blind_spots"]}
                        for r in valid if r["oracle"]["symbolic"]["blind_spots"]],
        "replay_failures": [{"sample": r["sample"], "actions": r["oracle"]["symbolic"]["replay_failures"]}
                            for r in valid if r["oracle"]["symbolic"]["replay_failures"]],
        "stop_reasons": dict(sorted({c["stop_reason"]: sum(x["stop_reason"] == c["stop_reason"] for x in calls) for c in calls}.items(), key=str)),
        "model_versions": sorted({c["model_version"] for c in calls}),
        "calls": len(calls), "api_calls": len(fresh),
        "usage": {k: sum((c["usage"] or {}).get(k, 0) or 0 for c in calls)
                  for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")},
        "cost_usd_all_calls": round(sum(cost(model, c["usage"] or {}) for c in calls), 4),
        "cost_usd_this_run": round(sum(cost(model, c["usage"] or {}) for c in fresh), 4),
    }
    if any("critic" in r for r in results):
        rounds = [r["critic"]["rounds_used"] for r in results]
        out["critic_passed"] = sum(r["critic"]["passed"] for r in results)
        out["rounds_used_counts"] = {k: rounds.count(k) for k in sorted(set(rounds))}
    return out


def markdown(config: dict, summary: dict) -> str:
    """Human summary table."""
    lines = [f"# Clean run {config['run_id']}", "",
             f"Model `{config['model']}` (API reported: {', '.join(sorted({v for s in summary.values() for v in s['model_versions']}))}); "
             f"N={config['n']}; generators: naive, {critic.LABEL}.", "",
             "| scenario | generator | valid | surplus≠∅ (of valid) | deficit≠∅ (of valid) | symcc: P⊄P_ref | blind spots | rounds | cost (all calls) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for key, s in summary.items():
        sc, gen = key.split("/")
        rounds = s.get("rounds_used_counts", "—")
        lines.append(f"| {sc} | {gen} | {s['valid']}/{s['n']} {s['validity_ci95']} | {s['nonempty_surplus']}/{s['valid']} {s['nonempty_surplus_ci95']} "
                     f"| {s['nonempty_deficit']}/{s['valid']} {s['nonempty_deficit_ci95']} | {s['symbolic_not_implies_reference']}/{s['valid']} "
                     f"| {len(s['blind_spots'])} | {rounds} | ${s['cost_usd_all_calls']:.3f} |")
    lines += ["", "Intervals: 95% Wilson. Surplus/deficit: enumeration over the scenario universe. "
              "symcc: realizable counterexamples (R1/R2 exclusion), per action."]
    return "\n".join(lines) + "\n"


def main() -> None:
    """Run (or replay) a clean run."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--model", required=True)
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--label", default="")
    p.add_argument("--generators", nargs="+", default=list(GENERATORS), choices=GENERATORS)
    p.add_argument("--scenarios", nargs="+", type=Path, default=DEFAULT_SCENARIOS)
    p.add_argument("--no-descriptions", action="store_true", help="include_descriptions=False")
    p.add_argument("--judge-sees-manifests", action="store_true")
    p.add_argument("--replay", action="store_true", help="serve every call from the cache; fail on a miss")
    p.add_argument("--cache", type=Path, default=ROOT / "cache/llm")
    args = p.parse_args()

    from pgi.llm.anthropic_provider import AnthropicProvider
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = "-".join(x for x in (stamp, "clean", args.label) if x)
    out = ROOT / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    llm = CachedLLM(AnthropicProvider() if not args.replay else _NoProvider(), args.cache, allow_api=not args.replay)
    ncfg = naive.NaiveConfig(args.model, include_descriptions=not args.no_descriptions)
    scfg = critic.SonderaConfig(args.model, include_descriptions=not args.no_descriptions,
                                judge_sees_manifests=args.judge_sees_manifests)
    inputs = [load_scenario_inputs(s) for s in args.scenarios]
    config = {"run_id": run_id, "created": stamp, "model": args.model, "n": args.n, "replay": args.replay,
              "generators": {"naive": ncfg.as_dict(), "sondera": scfg.as_dict()},
              "generators_run": args.generators,
              "request": {"sampling": "not sent (API default)", "thinking": {"type": "adaptive"},
                          "output_config": {"effort": ncfg.effort}, "max_tokens": ncfg.max_tokens,
                          "fallbacks": "none", "prompt_cache": "ephemeral breakpoint on last static system block"},
              "scenarios": {i.name: {"schema": str(i.schema_path.relative_to(ROOT)), "servers": list(i.servers),
                                     "hashes": i.hashes} for i in inputs},
              "versions": _tool_versions()}
    _dump(out / "config.json", config)
    for inp in inputs:  # the static prefix, stored once per scenario
        _dump(out / inp.name / "prompt_static.json", naive.build_request(inp, ncfg)[1]["system"])

    lock = threading.Lock()
    results: dict[str, list[dict]] = {}

    def scenario_job(inp: ScenarioInputs) -> None:
        for gen in args.generators:
            rows = []
            for i in range(args.n):
                d = out / inp.name / gen / f"sample_{i:02d}"
                row = run_naive(llm, inp, ncfg, i, d) if gen == "naive" else run_sondera(llm, inp, scfg, i, d)
                rows.append(row)
                with lock:
                    print(f"{inp.name} {gen} sample {i}: valid={row['oracle']['valid']} "
                          f"surplus={row['oracle'].get('enumeration', {}).get('surplus')} "
                          f"deficit={row['oracle'].get('enumeration', {}).get('deficit')}", flush=True)
            with lock:
                results[f"{inp.name}/{gen}"] = rows

    with ThreadPoolExecutor(max_workers=len(inputs)) as pool:
        for f in [pool.submit(scenario_job, inp) for inp in inputs]:
            f.result()
    summary = {k: summarize(args.model, results[k]) for k in sorted(results)}
    _dump(out / "summary.json", summary)
    (out / "summary.md").write_text(markdown(config, summary))
    print(f"\nwrote {out}\napi calls this run: {llm.api_calls}")


class _NoProvider:
    """Stand-in provider for --replay: any call is a bug (CachedLLM raises CacheMiss before reaching it)."""

    name = "none"

    def call(self, *a, **k):
        raise RuntimeError("replay mode reached the provider")

    text = model_version = usage = call


if __name__ == "__main__":
    main()
