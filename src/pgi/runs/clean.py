"""Clean runs: N samples per scenario per generator, scored by the oracle, written to runs/<id>/.

    uv run python -m pgi.runs.clean --model claude-haiku-5-5 --n 2 --label smoke
    uv run python -m pgi.runs.clean --replay runs/<id>          # cache only, zero API calls, new folder
    uv run python -m pgi.runs.clean --replay runs/<old> --inputs-from-git <commit>   # runs before snapshots
    uv run python -m pgi.runs.clean --model M --n N --cache-only --label L   # current inputs, cache only
    uv run python -m pgi.runs.clean --model M --n N --scenarios S --mutation NAME \
        [--compare-to runs/<clean>] [--fisher CASE ...]     # probe/attack: generators see mutated manifests

Layout: runs/<id>/config.json, summary.json, summary.md, inputs/<scenario>/ (snapshot of every input a
score depends on; generation and scoring read only from it), and per scenario/generator/sample:
response(s), policy.cedar, oracle.json. The static prompt prefix is stored once per scenario.
A replay takes model, N, generators, settings and inputs from the source run, never from the repo.
Samples within a scenario run sequentially (the prompt cache must be readable); scenarios run in parallel.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.metadata as md
import json
import math
import os
import shutil
import subprocess
import threading
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from pgi.analysis.defaults import default_reliance
from pgi.analysis.provenance import Sources, provenance
from pgi.generators import critic, naive
from pgi.generators.inputs import ScenarioInputs, load_scenario_inputs
from pgi.llm.cache import CachedLLM, Completion
from pgi.llm.pricing import cost
from pgi.mutators import load_mutations, mutate
from pgi.oracle.causes import causes
from pgi.oracle.enumeration import allowed, load_universe
from pgi.runs.compare import compare
from pgi.runs.compare import markdown as compare_markdown
from pgi.runs.judge import same_behaviour, score
from pgi.runs.snapshot import load_snapshot, snapshot, snapshot_from_git

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCENARIOS = [ROOT / "domains/assetopsbench/scenarios" / s
                     for s in ("s01_close_after_approval", "s02_site_scoped_reads", "s03_create_at_main")]
GENERATORS = ("naive", "sondera")


_RUN_DIR: Path | None = None  # set by atomic_run_dir: paths under it are recorded relative to it


@contextlib.contextmanager
def atomic_run_dir(runs_root: Path, run_id: str):
    """Yield runs_root/.tmp-<run_id>/; rename it to runs_root/<run_id>/ only if the block succeeds.

    On an exception the tmp folder stays, with a FAILED file holding the traceback, and the exception
    propagates. Paths inside the folder are written relative to it (see _dump), so the rename keeps them valid.
    """
    global _RUN_DIR
    final, tmp = Path(runs_root) / run_id, Path(runs_root) / f".tmp-{run_id}"
    if final.exists():
        raise FileExistsError(f"{final} exists; runs are never overwritten")
    if _RUN_DIR is not None:
        raise RuntimeError(f"another run is open in this process: {_RUN_DIR}")
    tmp.mkdir(parents=True, exist_ok=False)
    _RUN_DIR = tmp
    try:
        yield tmp
    except BaseException:
        (tmp / "FAILED").write_text(traceback.format_exc())
        raise
    finally:
        _RUN_DIR = None
    os.rename(tmp, final)


def _dump(path: Path, obj) -> None:
    """Write JSON, creating parents; refuse to overwrite. Paths under the open run folder become relative."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"{path} exists; runs are never overwritten")
    text = json.dumps(obj, indent=1, ensure_ascii=False, default=str)
    if _RUN_DIR is not None:
        text = text.replace(str(_RUN_DIR) + "/", "")
    path.write_text(text + "\n")


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


def literal_provenance(policy: Path, inp: ScenarioInputs) -> list[dict] | dict:
    """Provenance rows for one policy file, or {"error": ...} if it does not parse."""
    src = Sources.from_files(intent=inp.folder / "intent.md", trusted_schemas=list(inp.schema_parts.get("trusted", ())),
                             generated_schemas=list(inp.schema_parts.get("generated", ())),
                             manifests=dict(zip(inp.servers, inp.manifest_paths)))
    try:
        return provenance(policy, src)
    except ValueError as e:
        return {"error": str(e)}


def cause_tags(policy: Path, inp: ScenarioInputs, oracle: dict) -> dict | None:
    """Cause tags for a valid sample's surplus (explained by P_ref) and deficit (by the candidate)."""
    if not oracle["valid"]:
        return None
    e = oracle["enumeration"]
    return causes(policy, inp.reference, e["surplus"], e["deficit"], load_universe(inp.universe), inp.schema_path)


def default_reliance_rows(policy: Path, inp: ScenarioInputs, oracle: dict) -> list[dict] | None:
    """Default-reliance rows for a valid sample (pgi.analysis.defaults), against the defaults the server
    applies (the pinned manifests when the generator saw mutated ones); None for an invalid one."""
    if not oracle["valid"]:
        return None
    return default_reliance(policy, load_universe(inp.universe), inp.schema_path,
                            inp.defaults_manifests)


def run_naive(llm: CachedLLM, inp: ScenarioInputs, cfg: naive.NaiveConfig, i: int, d: Path,
              frame: ScenarioInputs | None = None) -> dict:
    """One naive sample: generate from `inp`, write, score.

    `frame` is the measuring frame (schema, universe, reference, server defaults) the policy is scored in;
    by default the inputs it was generated from. A probe passes the clean inputs here so that both arms
    are scored under one fixed frame. Provenance always reads what the generator saw (`inp`).
    """
    frame = frame or inp
    s = naive.generate(llm, inp, cfg, i)
    (d / "policy.cedar").parent.mkdir(parents=True, exist_ok=True)
    (d / "policy.cedar").write_text(s.policy_text + "\n" if s.policy_text else "")
    _dump(d / "response.json", _call_record(s.completion) | {"extraction": s.extraction})
    oracle = score(d / "policy.cedar", frame)
    tags = cause_tags(d / "policy.cedar", frame, oracle)
    _dump(d / "oracle.json", oracle | {"cause_tags": tags})
    prov = literal_provenance(d / "policy.cedar", inp)
    _dump(d / "provenance.json", prov)
    rel = default_reliance_rows(d / "policy.cedar", frame, oracle)
    _dump(d / "defaults.json", rel)
    return {"sample": i, "calls": [_call_record(s.completion)], "oracle": oracle, "cause_tags": tags, "provenance": prov,
            "default_reliance": rel}


def run_sondera(llm: CachedLLM, inp: ScenarioInputs, cfg: critic.SonderaConfig, i: int, d: Path,
                frame: ScenarioInputs | None = None) -> dict:
    """One Sondera-style sample: up to max_rounds of generate + critics (in `inp`'s world), then score the
    output in `frame` (default `inp`; see run_naive). Round-to-round behaviour is compared in `inp`'s world."""
    frame = frame or inp
    res = critic.run(llm, inp, cfg, i, d)
    calls = []
    for r in res.rounds:
        rec = {"round": r.index, "extraction": r.extraction, "generation": _call_record(r.completion),
               "deterministic": r.deterministic.as_dict(), "judge": _call_record(r.judge_completion),
               "judge_passed": r.judge_passed, "passed": r.passed}
        _dump(d / f"round{r.index}.json", rec)
        calls += [rec["generation"], rec["judge"]]
    (d / "policy.cedar").write_text(res.final_policy + "\n" if res.final_policy else "")
    oracle = score(d / "policy.cedar", frame)
    pairs = []
    for a, b in zip(res.rounds, res.rounds[1:]):  # consecutive rounds: did the judge move on unchanged behaviour?
        same = same_behaviour(a.policy_path, b.policy_path, inp)
        pairs.append({"rounds": [a.index, b.index], "valid": [a.deterministic.validation.ok, b.deterministic.validation.ok],
                      "same_text": a.policy_text == b.policy_text, "same_behaviour": same,
                      "judge": [a.judge_passed, b.judge_passed], "judge_changed": a.judge_passed != b.judge_passed})
    crit = {"passed": res.passed, "rounds_used": res.rounds_used, "round_pairs": pairs}
    tags = cause_tags(d / "policy.cedar", frame, oracle)
    _dump(d / "oracle.json", oracle | {"critic": crit, "cause_tags": tags})
    prov = literal_provenance(d / "policy.cedar", inp)
    _dump(d / "provenance.json", prov)
    rel = default_reliance_rows(d / "policy.cedar", frame, oracle)
    _dump(d / "defaults.json", rel)
    return {"sample": i, "calls": calls, "oracle": oracle, "critic": crit, "cause_tags": tags, "provenance": prov,
            "default_reliance": rel}


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """95% Wilson score interval for k successes in n trials."""
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


TRUSTED_SOURCES = ("intent", "trusted_schema")  # provenance classes that come from the trusted channel


def summarize(model: str, results: list[dict], case_ids: list[str] | None = None,
              reference_allow: list[str] | None = None) -> dict:
    """Per scenario x generator: validity, surplus/deficit shares, clean envelope, per-request allow counts,
    symcc, blind spots, cost; for the critic, pass rates and judge flips on unchanged behaviour."""
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
        "reference_allow_set": sorted(reference_allow) if reference_allow is not None else None,
        "allow_counts": {c: {"k": (k := sum(c in r["oracle"]["enumeration"]["allow_set"] for r in valid)),
                             "n": nv, "ci95": wilson(k, nv)} for c in (case_ids or [])},
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
    parsed = [r["provenance"] for r in results if isinstance(r.get("provenance"), list)]
    lits: dict[str, dict] = {}
    for rows in parsed:
        for row in rows:
            e = lits.setdefault(row["literal"], {"kind": row["kind"], "role": row.get("role", "value"),
                                                 "samples": 0, "sources": row["sources"]})
            e["samples"] += 1
    out["literal_provenance"] = dict(sorted(lits.items(), key=lambda kv: (-kv[1]["samples"], kv[0])))
    out["value_literals_without_trusted_source"] = [
        lit for lit, e in out["literal_provenance"].items()
        if e["role"] == "value" and not any(c in e["sources"] for c in TRUSTED_SOURCES)]
    out["provenance_parsed"] = len(parsed)
    tag_counts: dict[str, dict] = {"surplus": {}, "deficit": {}}
    for r in results:
        for side in ("surplus", "deficit"):
            for case, ex in ((r.get("cause_tags") or {}).get(side) or {}).items():
                for tag in (ex["tag"] if isinstance(ex["tag"], list) else [ex["tag"]]):
                    per = tag_counts[side].setdefault(case, {})
                    per[tag] = per.get(tag, 0) + 1
    out["cause_tag_counts"] = {s: dict(sorted(v.items())) for s, v in tag_counts.items()}
    checked = [r["default_reliance"] for r in results if isinstance(r.get("default_reliance"), list)]
    relying = [{f'{x["tool"]}.{x["field"]}' for x in rows if x["verdict"] == "relies"} for rows in checked]
    out["default_reliance"] = {
        "samples_relying": sum(bool(f) for f in relying), "samples_checked": len(checked),
        "samples_relying_ci95": wilson(sum(bool(f) for f in relying), len(checked)),
        "samples_by_field": dict(sorted(Counter(f for fs in relying for f in fs).items())),
        "verdicts": dict(sorted(Counter(x["verdict"] for rows in checked for x in rows).items()))}
    if any("critic" in r for r in results):
        rounds = [r["critic"]["rounds_used"] for r in results]
        passed = [r for r in results if r["critic"]["passed"]]
        out["critic_passed"] = len(passed)
        out["critic_pass_share"] = round(len(passed) / n, 3) if n else None
        out["critic_pass_ci95"] = wilson(len(passed), n)
        first = sum(r["critic"]["rounds_used"] == 1 for r in passed)
        out["critic_passed_round1"] = first
        out["critic_passed_round1_share"] = round(first / n, 3) if n else None
        out["critic_passed_round1_ci95"] = wilson(first, n)
        to_pass = [r["critic"]["rounds_used"] for r in passed]
        out["rounds_to_pass_counts"] = {k: to_pass.count(k) for k in sorted(set(to_pass))}
        out["rounds_used_counts"] = {k: rounds.count(k) for k in sorted(set(rounds))}
        same = [p for r in results for p in r["critic"].get("round_pairs", []) if p["same_behaviour"] is True]
        out["judge_flips_on_same_behaviour"] = {"flips": sum(p["judge_changed"] for p in same), "pairs": len(same)}
    return out


def markdown(config: dict, summary: dict) -> str:
    """Human summary table."""
    lines = [f"# {config.get('kind', 'clean').capitalize()} run {config['run_id']}", "",
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
    crit = {k: s for k, s in summary.items() if "critic_passed" in s}
    if crit:
        lines += ["", f"## {critic.LABEL}: critics", "",
                  "| scenario | passed both critics | passed in round 1 | rounds to pass | judge flips on unchanged behaviour |",
                  "|---|---|---|---|---|"]
        for key, s in crit.items():
            f = s["judge_flips_on_same_behaviour"]
            lines.append(f"| {key.split('/')[0]} | {s['critic_passed']}/{s['n']} {s['critic_pass_ci95']} "
                         f"| {s['critic_passed_round1']}/{s['n']} {s['critic_passed_round1_ci95']} "
                         f"| {s['rounds_to_pass_counts']} | {f['flips']}/{f['pairs']} |")
        lines += ["", "Judge flips: consecutive rounds whose policies behave identically (equal allow-sets, symcc "
                  "implication both ways on every action) but whose judge verdicts differ / all such pairs."]
    scenarios = sorted({k.split("/")[0] for k in summary})
    lines += _literal_tables(summary, scenarios, "value")
    for sc in scenarios:
        gens = [k.split("/")[1] for k in summary if k.split("/")[0] == sc]
        first = summary[f"{sc}/{gens[0]}"]
        if not first.get("allow_counts"):
            continue
        ref = set(first.get("reference_allow_set") or [])
        lines += ["", f"### {sc}: allow counts per request", "",
                  "| case | P_ref | " + " | ".join(gens) + " |", "|---|---|" + "---|" * len(gens)]
        for case in first["allow_counts"]:
            cells = [f"{summary[f'{sc}/{g}']['allow_counts'][case]['k']}/{summary[f'{sc}/{g}']['allow_counts'][case]['n']}"
                     for g in gens]
            lines.append(f"| {case} | {'✓' if case in ref else ''} | " + " | ".join(cells) + " |")
        lines += ["", "k/n = valid samples allowing the case / valid samples (enumeration). Wilson intervals in summary.json."]
    lines += ["", "## Default reliance", "",
              "| scenario | generator | samples relying on a default (of checked) | by tool.field | verdicts |",
              "|---|---|---|---|---|"]
    for key, s in summary.items():
        d = s.get("default_reliance") or {}
        if not d:
            continue
        by = ", ".join(f"{f}: {n}" for f, n in d["samples_by_field"].items()) or "—"
        lines.append(f"| {key.split('/')[0]} | {key.split('/')[1]} | {d['samples_relying']}/{d['samples_checked']} "
                     f"| {by} | {d['verdicts']} |")
    lines += ["", "Relies: the policy allows the request with the defaulted field omitted, yet denies an explicit "
              "alternative value of it (pgi.analysis.defaults). Checked = valid samples."]
    lines += _literal_tables(summary, scenarios, "scope")
    for sc in scenarios:
        rows = [(side, case, k.split("/")[1], tag, n)
                for k, s in summary.items() if k.split("/")[0] == sc
                for side in ("surplus", "deficit")
                for case, tags in s.get("cause_tag_counts", {}).get(side, {}).items()
                for tag, n in tags.items()]
        if not rows:
            continue
        lines += ["", f"### {sc}: cause tags", "", "| side | case | generator | tag | samples |", "|---|---|---|---|---|"]
        lines += [f"| {side} | {case} | {g} | `{tag}` | {n} |" for side, case, g, tag, n in sorted(rows)]
        lines += ["", "Surplus: the reference conjunct that denies the case. Deficit: the candidate conjunct that denies it "
                  "(first blocker of the prefix scan; sole blockers in each sample's oracle.json)."]
    return "\n".join(lines) + "\n"


def _literal_tables(summary: dict, scenarios: list[str], role: str) -> list[str]:
    """One table per scenario of literals with this role (value literals carry a trusted-source flag)."""
    lines = []
    for sc in scenarios:
        gens = [k.split("/")[1] for k in summary if k.split("/")[0] == sc]
        lits: dict[str, dict] = {}
        for g in gens:
            for lit, e in summary[f"{sc}/{g}"].get("literal_provenance", {}).items():
                if e.get("role", "value") == role:
                    lits.setdefault(lit, e)
        if not lits:
            continue
        title = "value literals" if role == "value" else "scope names"
        flag = " trusted source |" if role == "value" else ""
        lines += ["", f"### {sc}: {title}", "",
                  "| literal | " + " | ".join(gens) + " |" + flag + " sources |",
                  "|---|" + "---|" * len(gens) + ("---|" if role == "value" else "") + "---|"]
        for lit, e in lits.items():
            cells = [f"{summary[f'{sc}/{g}']['literal_provenance'].get(lit, {}).get('samples', 0)}"
                     f"/{summary[f'{sc}/{g}']['provenance_parsed']}" for g in gens]
            trusted = (" yes |" if any(c in e["sources"] for c in TRUSTED_SOURCES) else " **no** |") if role == "value" else ""
            lines.append(f"| `{lit}` | " + " | ".join(cells) + " |" + trusted + f" {', '.join(e['sources']) or '**none**'} |")
        note = ("Value literals: constants compared in conditions (strings, longs, non-action entity ids). "
                "Trusted source = intent or trusted schema. " if role == "value" else
                "Scope names: actions, scope entities and entity types. ")
        lines += ["", note + "k/n = samples using it / samples whose policy parses. Whole-token, case-sensitive."]
    return lines


def main() -> None:
    """Run (or replay) a clean run."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--model")
    p.add_argument("--n", type=int)
    p.add_argument("--label", default="")
    p.add_argument("--generators", nargs="+", default=list(GENERATORS), choices=GENERATORS)
    p.add_argument("--scenarios", nargs="+", type=Path, default=DEFAULT_SCENARIOS)
    p.add_argument("--no-descriptions", action="store_true", help="include_descriptions=False")
    p.add_argument("--judge-sees-manifests", action="store_true")
    p.add_argument("--replay", type=Path, metavar="RUN_DIR",
                   help="re-run RUN_DIR from the cache into a new folder (its settings and inputs); fail on a miss")
    p.add_argument("--inputs-from-git", metavar="COMMIT",
                   help="with --replay, for a run without inputs/: rebuild them from git, checked against its hashes")
    p.add_argument("--cache-only", action="store_true",
                   help="current repo inputs, but every LLM call must hit the cache (re-score with new references)")
    p.add_argument("--mutation", help="a named mutation from <domain>/mutations.yaml (pgi.mutators)")
    p.add_argument("--compare-to", type=Path, metavar="RUN_DIR", help="clean run to compare with (pgi.runs.compare)")
    p.add_argument("--fisher", nargs="*", default=[], help="cases for the one-sided Fisher test in the comparison")
    p.add_argument("--cache", type=Path, default=ROOT / "cache/llm")
    args = p.parse_args()
    src = None
    if args.replay:
        src = json.loads((args.replay / "config.json").read_text())
        if args.model or args.n:
            p.error("--replay takes model and N from the source run")
        args.model, args.n, args.generators = src["model"], src["n"], src["generators_run"]
        args.no_descriptions = not src["generators"]["naive"]["include_descriptions"]
        args.judge_sees_manifests = src["generators"]["sondera"]["judge_sees_manifests"]
    elif not (args.model and args.n):
        p.error("--model and --n are required unless --replay is given")
    elif args.inputs_from_git:
        p.error("--inputs-from-git needs --replay")
    mutation = None
    if args.mutation:
        if args.replay:
            p.error("--replay takes the (possibly mutated) inputs from the source run; drop --mutation")
        domains = {Path(s).resolve().parents[1] for s in args.scenarios}
        if len(domains) != 1:
            p.error("--mutation needs scenarios from one domain")
        mutation = load_mutations(domains.pop() / "mutations.yaml")[args.mutation]
    kind = (f"{mutation.kind}-{mutation.name}" if mutation
            else (src.get("kind", "clean") if src else "clean"))

    from pgi.llm.anthropic_provider import AnthropicProvider
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = "-".join(x for x in (stamp, kind, args.label) if x)
    with atomic_run_dir(ROOT / "runs", run_id) as out:
        offline = bool(args.replay or args.cache_only)
        llm = CachedLLM(_NoProvider() if offline else AnthropicProvider(), args.cache, allow_api=not offline)
        ncfg = naive.NaiveConfig(args.model, include_descriptions=not args.no_descriptions)
        scfg = critic.SonderaConfig(args.model, include_descriptions=not args.no_descriptions,
                                    judge_sees_manifests=args.judge_sees_manifests)
        records: list[dict] = []
        if mutation:
            pairs = [mutate(mutation, load_scenario_inputs(s), out / "inputs" / Path(s).name) for s in args.scenarios]
            inputs, records = [i for i, _ in pairs], [r for _, r in pairs]
        else:
            inputs = _inputs(args, src, out / "inputs")
        config = {"run_id": run_id, "created": stamp, "kind": kind, "model": args.model, "n": args.n,
                  "replay": bool(args.replay), "replay_of": args.replay.name if args.replay else None,
                  "cache_only": offline,
                  "mutation": ({**mutation.as_dict(), "per_scenario": records} if mutation
                               else (src.get("mutation") if src else None)),
                  "inputs": "inputs/<scenario>/ (snapshot; generation and scoring read only from it)"
                            + (f"; rebuilt from git {args.inputs_from_git}" if args.inputs_from_git else ""),
                  "generators": {"naive": ncfg.as_dict(), "sondera": scfg.as_dict()},
                  "generators_run": args.generators,
                  "request": {"sampling": "not sent (API default)", "thinking": {"type": "adaptive"},
                              "output_config": {"effort": ncfg.effort}, "max_tokens": ncfg.max_tokens,
                              "fallbacks": "none", "prompt_cache": "ephemeral breakpoint on last static system block"},
                  "scenarios": {i.name: {"schema": str(i.schema_path.relative_to(out)), "servers": list(i.servers),
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
        cases = {}
        for inp in inputs:
            universe = load_universe(inp.universe)
            cases[inp.name] = (list(universe.requests), sorted(allowed(inp.reference, universe, inp.schema_path)))
        summary = {k: summarize(args.model, results[k], *cases[k.split("/")[0]]) for k in sorted(results)}
        _dump(out / "summary.json", summary)
        (out / "summary.md").write_text(markdown(config, summary))
        if args.compare_to:
            res = compare(args.compare_to, out, args.fisher)
            _dump(out / "comparison.json", {"clean": args.compare_to.name, "mutated": run_id,
                                            "fisher_cases": args.fisher, "result": res})
            (out / "comparison.md").write_text(compare_markdown(res, args.compare_to.name, run_id))
    print(f"\nwrote {ROOT / 'runs' / run_id}\napi calls this run: {llm.api_calls}")


def _inputs(args, src: dict | None, dest: Path) -> list[ScenarioInputs]:
    """Snapshot the inputs into dest/<scenario>/ and load them back from there (hash-checked)."""
    if src is None:
        return [snapshot(load_scenario_inputs(s), dest / Path(s).name) for s in args.scenarios]
    out = []
    for name, rec in src["scenarios"].items():
        if (args.replay / "inputs" / name).is_dir():
            if args.inputs_from_git:
                raise SystemExit(f"{args.replay} has its own inputs/; drop --inputs-from-git")
            shutil.copytree(args.replay / "inputs" / name, dest / name)
            snap = load_snapshot(dest / name)
        elif args.inputs_from_git:
            domain = Path(rec["schema"]).parents[1]  # legacy record: <domain>/schema/<file>, repo-relative
            snap = snapshot_from_git(ROOT, args.inputs_from_git, str(domain / "scenarios" / name), dest / name, rec["hashes"])
        else:
            raise SystemExit(f"{args.replay} has no inputs/{name}; pass --inputs-from-git <commit>")
        if {k: snap.hashes.get(k) for k in rec["hashes"]} != rec["hashes"]:
            raise SystemExit(f"{name}: inputs do not match the hashes {args.replay} recorded")
        out.append(snap)
    return out


class _NoProvider:
    """Stand-in provider for --replay: any call is a bug (CachedLLM raises CacheMiss before reaching it)."""

    name = "none"

    def call(self, *a, **k):
        raise RuntimeError("replay mode reached the provider")

    text = model_version = usage = call


if __name__ == "__main__":
    main()
