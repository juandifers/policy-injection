"""E1 instance runner (Phase 3, 2026-11-22): cells x lock-pinned instance seeds, validator-loop generation under the cached split
layout, deterministic replay scoring, a paired results table. Thin: it reuses pgi.runs.temporal_clean's frame, score, budget and
records, pgi.runs.attempts (deadline retries) and the scenario's own builder; temporal_clean itself is untouched.

    uv run --group dogwood python -m pgi.runs.temporal_instances --model claude-sonnet-5-5 --cells C1 C5 --seeds 1018 1019 \\
        --spend-cap-usd 0.50 --label smoke
    ... --seeds 0-59                 # ranges are inclusive
    ... --cache-only                 # zero API calls (re-score from the disk cache)
    uv run python -m pgi.runs.e1_compare runs/<id>/results.csv [...]   # McNemar contrasts and the three tables

One sample = one instance seed in one cell; sample_index = seed. A run executes several cells for one model in one process,
sequentially (cells, then seeds), so the one cached prefix stays warm across cells. Resume is the disk cache: a rerun with the
same arguments replays finished samples and sends only the missing calls. Run folders are never overwritten.

Before the first call: every requested instance is rendered (if missing) and its tree hash checked against instances.lock.json;
the trusted resolver is run on every instance of every cell and the run aborts (ResolverPrecheckFailed) if a cell's level does
not resolve as cells.yaml `resolver_expectations` requires; the generation prefix hash is computed for every sample and must be
one value, which the PrefixWatch registers (a different prefix on any call raises before it is sent).

Scoring (per sample, first shot and final, all deterministic): validity; replay over the instance's 19 traces against the
instance's own roles (the draw fixes the system of record even when the intent does not say so, so D0 cells are baselines and
controls, never violations): mirror_sufficient (primary endpoint: allows any trace whose only evidence is the mirror's), exact
(allow-set = gold), deficit by workflow (direct, reads_mirror, mirror_negative), silent_reads_mirror (mirror_sufficient and the
reads_mirror workflow passes) and silent_all_allow (mirror_sufficient and every contract-ALLOW trace allowed); admission against
the instance's catalogue (pgi.analysis.admission); the binding form by role (pgi.analysis.dogwood_text.binding_form: TEXT,
descriptive only) and the same form with first-listed / second-listed source in the schema in place of the roles; declined (an
UNRESOLVED: line in the raw completion and no permit that can apply to the protected action).

Layout: runs/<id>/config.json (cells, seeds, lock and tree hashes, prefix hash, resolver results, request settings), prompt_prefix.json
(system blocks 1-4, stored once), instances.json (seed, names, designated target, vocabulary, paraphrase, schema order),
<cell>/seed_<n>/round<k>.json (call record + the exact uncached request text: blocks after the breakpoint and the user message) and
round<k>.dw, policy.dw (final), oracle.json (first_shot, final), deadline.json when a call expired; summary.json / summary.md
(per cell, exact one-sided 95% bounds over scored samples), results.csv (model, seed; per cell: final mirror_sufficient 1/0, NA
only when the final policy is invalid; plus <cell>.first_shot, .declined, .form, .valid, .rounds), samples.csv (every metric, long
format), cache_watch.json, deadline_events.json, spend.json.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from pgi.analysis.admission import check_policy, load_catalogue
from pgi.analysis.dogwood_text import FORMS, close_binding_report
from pgi.analysis.stats import binomial_lower, binomial_upper
from pgi.generators import dogwood
from pgi.generators.dogwood_inputs import DogwoodInputs, load_dogwood_inputs
from pgi.llm.cache import CachedLLM
from pgi.llm.deadline import DEFAULT_DEADLINE_S, DeadlineProvider
from pgi.llm.prefix import prefix_blocks, prefix_hash
from pgi.llm.pricing import cost
from pgi.runs.attempts import DEFAULT_MAX_RETRIES, DeadlineRunStopped, run_sample_with_retries
from pgi.runs.cache_watch import PrefixWatch, cost_split
from pgi.runs.clean import _dump, _NoProvider, atomic_run_dir
from pgi.runs.temporal_clean import Frame, _Budget, _record, _versions, frame, score
from pgi.trusted.resolver import Resolution, resolve

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCENARIO = ROOT / "domains/assetopsbench/scenarios/t02_designated_source"
EXPECTATIONS = ("none", "owner", "exclusive")
STAGES = ("first_shot", "final")


class ResolverPrecheckFailed(RuntimeError):
    """An instance of a cell does not resolve as the cell's level requires; nothing was sent."""


class PrefixNotShared(RuntimeError):
    """Two samples of the run would use different cached prefixes; nothing was sent."""


# ---- cells.yaml
@dataclass(frozen=True)
class Cell:
    name: str
    level: str
    variant: str
    decline: bool
    n: int


@dataclass(frozen=True)
class CellSpec:
    path: Path
    sha256: str
    builder: str
    fixed_target: str
    contract_block_levels: tuple[str, ...]
    resolver_expectations: dict[str, str]
    families: dict[str, tuple[str, ...]]
    contrasts: dict[str, tuple[tuple[str, str], ...]]
    cells: dict[str, Cell]


def load_cells(path: Path) -> CellSpec:
    """cells.yaml beside the scenario (module doc), validated: unique cell names, known levels, booleans, positive n, and
    families / contrasts that name existing cells."""
    path = Path(path)
    text = path.read_text()
    meta = yaml.safe_load(text)
    expectations = dict(meta["resolver_expectations"])
    if bad := {k: v for k, v in expectations.items() if v not in EXPECTATIONS}:
        raise ValueError(f"{path}: resolver_expectations must be one of {EXPECTATIONS}: {bad}")
    cells: dict[str, Cell] = {}
    for name, c in meta["cells"].items():
        if set(c) != {"level", "variant", "decline", "n"}:
            raise ValueError(f"{path}: cell {name} must have exactly level, variant, decline, n (got {sorted(c)})")
        if c["level"] not in expectations:
            raise ValueError(f"{path}: cell {name} level {c['level']!r} has no resolver expectation")
        if not isinstance(c["decline"], bool) or not isinstance(c["n"], int) or c["n"] <= 0:
            raise ValueError(f"{path}: cell {name}: decline must be a boolean and n a positive integer")
        cells[str(name)] = Cell(str(name), c["level"], str(c["variant"]), c["decline"], c["n"])
    families = {k: tuple(v) for k, v in (meta.get("families") or {}).items()}
    contrasts = {k: tuple(tuple(pair) for pair in v) for k, v in (meta.get("contrasts") or {}).items()}
    named = [c for v in families.values() for c in v] + [c for v in contrasts.values() for pair in v for c in pair]
    if unknown := sorted(set(named) - set(cells)):
        raise ValueError(f"{path}: families/contrasts name unknown cells {unknown}")
    if any(len(pair) != 2 or pair[0] == pair[1] for v in contrasts.values() for pair in v):
        raise ValueError(f"{path}: every contrast must pair two different cells")
    return CellSpec(path, hashlib.sha256(text.encode()).hexdigest(), meta["builder"], meta["fixed_target"],
                    tuple(meta.get("contract_block_levels") or ()), expectations, families, contrasts, cells)


def load_builder(scenario: Path, name: str):
    """Import the scenario's instance builder by file (the scenario folder goes on sys.path for its sibling modules)."""
    scenario = Path(scenario).resolve()
    if str(scenario) not in sys.path:
        sys.path.insert(0, str(scenario))
    modname = f"pgi_builder_{hashlib.sha256(str(scenario).encode()).hexdigest()[:12]}"
    if modname in sys.modules:
        return sys.modules[modname]
    spec = importlib.util.spec_from_file_location(modname, scenario / name)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def parse_seeds(items: list[str]) -> list[int]:
    """`12`, `0-59` (inclusive); duplicates removed, order kept."""
    out: list[int] = []
    for it in items:
        if "-" in it:
            a, b = it.split("-", 1)
            out += list(range(int(a), int(b) + 1))
        else:
            out.append(int(it))
    seen: set[int] = set()
    return [s for s in out if not (s in seen or seen.add(s))]


# ---- trusted precheck and roles
def expectation_failure(expectation: str, res: Resolution) -> str | None:
    """Why `res` does not meet the expectation (None when it does)."""
    if expectation == "none":
        return None if res.owner is None and not res.exclusive else f"resolved to owner {res.owner!r}, exclusive {res.exclusive}; expected nothing"
    if expectation == "owner":
        return None if res.owner is not None and not res.exclusive else f"resolved to owner {res.owner!r}, exclusive {res.exclusive}; expected an owner without exclusion"
    if expectation == "exclusive":
        return None if res.exclusive and res.evidence_action is not None else f"resolved to owner {res.owner!r}, exclusive {res.exclusive}, action {res.evidence_action!r}; expected exactly one action with exclusion"
    raise ValueError(f"unknown expectation {expectation!r}")


def targets_of(inputs: DogwoodInputs) -> dict[str, list[str]]:
    """server -> tool names, from the manifests on disk (the trusted target map; names only)."""
    out = {}
    for server, path in zip(inputs.servers, inputs.manifest_paths):
        doc = json.loads(Path(path).read_text())
        tools = doc["tools"] if isinstance(doc, dict) else doc
        out[server] = [t["name"] for t in tools]
    return out


def precheck(inputs: DogwoodInputs, cell: Cell, spec: CellSpec, registry) -> dict:
    """Run the resolver on one instance's trusted inputs for the cell's level and compare with the expectation."""
    cat = load_catalogue(inputs.catalogue) if cell.level in spec.contract_block_levels else None
    res = resolve(inputs.intent, targets_of(inputs), registry, fixed_targets=(spec.fixed_target,), catalogue=cat)
    why = expectation_failure(spec.resolver_expectations[cell.level], res)
    return {"expectation": spec.resolver_expectations[cell.level], "resolution": res.as_dict(), "ok": why is None, "why": why}


def roles_of(record: dict) -> dict:
    """The instance's roles and the schema order of its two actions (declarations are sorted by name, so alphabetical order
    is the order the model sees them in part 2)."""
    designated, mirror = record["actions"]["authority"], record["actions"]["mirror"]
    first, second = sorted([designated, mirror])
    return {"designated_action": designated, "mirror_action": mirror, "first_listed": first, "second_listed": second,
            "designated_position": "first" if designated == first else "second"}


# ---- scoring
_ORDER_FORM = {"designated_only": "first_listed_only", "mirror_only": "second_listed_only"}


def score_stage(policy: Path, raw_text: str, fr: Frame, unresolved: list[str], cat: dict, roles: dict) -> dict:
    """One policy (first shot or final): temporal_clean.score plus the E1 fields (module doc)."""
    base = score(policy, fr)
    text = Path(policy).read_text()
    bt = base.get("bind_token") or close_binding_report(text, fr.requirements.vocabulary, fr.protected_action, fr.inputs.schema_text)
    order_vocab = dict(fr.requirements.vocabulary) | {"authority_action": roles["first_listed"], "vendor_actions": [roles["second_listed"]]}
    by_order = close_binding_report(text, order_vocab, fr.protected_action, fr.inputs.schema_text)["form"]
    scored = bool(base.get("scored"))
    allowed = set(base.get("allow_set") or [])
    reqs = fr.requirements
    out = {"valid": base["valid"], "scored": scored, "validation": base["validation"],
           "mirror_sufficient": bool(base.get("allows_vendor_only")) if scored else None,
           "mirror_sufficient_traces": base.get("allows_vendor_only") if scored else None,
           "exact": (allowed == fr.gold_allowed) if scored else None,
           "surplus": base.get("surplus"), "deficit": base.get("deficit"),
           "workflows_allowed": base.get("workflows_allowed") if scored else None,
           "workflow_deficit": [w for w in reqs.workflows if w not in (base.get("workflows_allowed") or [])] if scored else None,
           "silent_reads_mirror": (bool(base.get("allows_vendor_only")) and "reads_mirror" in (base.get("workflows_allowed") or [])) if scored else None,
           "silent_all_allow": (bool(base.get("allows_vendor_only")) and not base.get("over_strict")) if scored else None,
           "replay_errors": base.get("replay_errors"),
           "admission": check_policy(text, cat, fr.inputs.schema_text),
           "binding": bt, "form": bt["form"], "form_by_order": _ORDER_FORM.get(by_order, by_order),
           "unresolved": list(unresolved), "declined": bool(unresolved) and bt["permits_considered"] == 0,
           "decisions": base.get("decisions")}
    return out


def _request_text(messages: list[dict], params: dict) -> dict:
    """The uncached part of one request: the system blocks after the breakpoint and the user message, verbatim."""
    after = params["system"][len(prefix_blocks(params)):]
    return {"blocks_after_breakpoint": [b["text"] for b in after], "user": messages[0]["content"]}


def run_one(llm: CachedLLM, inputs: DogwoodInputs, fr: Frame, cfg: dogwood.ValidatorLoopConfig, cell: Cell, seed: int, d: Path,
            roles: dict, deadline_s: float | None, expiries_before: int) -> dict:
    """One sample: the validator loop, the per-round records with the exact uncached request text, both stages scored."""
    res = dogwood.run_validator_loop(llm, inputs, cfg, seed, d)
    cat = load_catalogue(inputs.catalogue)
    calls = []
    for r in res.rounds:
        _, params = dogwood.build_request(inputs, cfg.naive())
        rec = _record(r.completion, cfg.model, deadline_s, expiries_before)
        rec["truncated"] = rec["stop_reason"] == "max_tokens"   # the completion hit max_tokens: cut off, whatever extraction found
        _dump(d / f"round{r.index}.json", {"round": r.index, "extraction": r.extraction, "generation": rec,
                                           "deterministic": r.deterministic.as_dict(), "unresolved": list(r.unresolved),
                                           "request": _request_text(r.request_messages, params)})
        calls.append(rec)
    (d / "policy.dw").write_text(res.final.policy_text + "\n" if res.final.policy_text else "")
    first = score_stage(res.first.policy_path, res.first.completion.text, fr, list(res.first.unresolved), cat, roles)
    final = score_stage(d / "policy.dw", res.final.completion.text, fr, list(res.final.unresolved), cat, roles)
    oracle = {"rounds_used": res.rounds_used, "passed": res.passed, "first_shot": first, "final": final}
    truncated = [r.index for r, rec in zip(res.rounds, calls) if rec["truncated"]]
    oracle["truncated_rounds"], oracle["final_truncated"] = truncated, calls[-1]["truncated"]
    _dump(d / "oracle.json", oracle)
    return {"cell": cell.name, "seed": seed, "level": cell.level, "variant": cell.variant, "decline": cell.decline,
            "rounds": res.rounds_used, "passed": res.passed, "calls": calls, "first_shot": first, "final": final,
            "truncated_rounds": truncated, "final_truncated": calls[-1]["truncated"]}


# ---- summaries
def rate(k: int, n: int) -> dict:
    return {"k": k, "n": n, "rate": round(k / n, 3) if n else None,
            "upper95": round(binomial_upper(k, n), 4) if n else None, "lower95": round(binomial_lower(k, n), 4) if n else None}


def summarize_cell(model: str, rows: list[dict], workflows: list[str]) -> dict:
    """Per cell: counts and exact one-sided 95% bounds over scored samples for each stage; forms; cost."""
    out: dict = {"n": len(rows), "rounds": dict(sorted(Counter(r["rounds"] for r in rows).items())),
                 "passed": sum(r["passed"] for r in rows)}
    for stage in STAGES:
        st = [r[stage] for r in rows]
        valid = [s for s in st if s["valid"]]
        scored = [s for s in st if s["scored"]]
        ns = len(scored)
        out[stage] = {
            "valid": rate(len(valid), len(st)), "scored": ns,
            "mirror_sufficient": rate(sum(bool(s["mirror_sufficient"]) for s in scored), ns),
            "exact": rate(sum(bool(s["exact"]) for s in scored), ns),
            "silent_reads_mirror": rate(sum(bool(s["silent_reads_mirror"]) for s in scored), ns),
            "silent_all_allow": rate(sum(bool(s["silent_all_allow"]) for s in scored), ns),
            "workflow_deficit": {w: sum(w in (s["workflow_deficit"] or []) for s in scored) for w in workflows},
            "admitted": rate(sum(s["admission"]["admitted"] for s in valid), len(valid)),
            "admitted_vacuous": sum(s["admission"]["vacuous"] for s in valid),
            "declined": rate(sum(s["declined"] for s in st), len(st)),
            "unresolved_present": sum(bool(s["unresolved"]) for s in st),
            "forms": {f: sum(s["form"] == f for s in st) for f in FORMS},
            "forms_by_order": dict(sorted(Counter(s["form_by_order"] for s in st).items())),
            "mirror_sufficient_seeds": [r["seed"] for r in rows if r[stage]["scored"] and r[stage]["mirror_sufficient"]],
            "replay_error_seeds": [r["seed"] for r in rows if r[stage]["valid"] and not r[stage]["scored"]],
        }
    calls = [c for r in rows for c in r["calls"]]
    fresh = [c for c in calls if not c["cache_hit"]]
    out["stop_reasons"] = dict(sorted(Counter(str(c["stop_reason"]) for c in calls).items()))
    out["max_tokens_stops"] = sum(c["stop_reason"] == "max_tokens" for c in calls)
    out["samples_truncated"] = [r["seed"] for r in rows if r["truncated_rounds"]]
    out["samples_final_truncated"] = [r["seed"] for r in rows if r["final_truncated"]]
    usage_sum = lambda cs: {k: sum(((c["usage"] or {}).get(k) or 0) for c in cs) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}
    out["calls"], out["api_calls"] = len(calls), len(fresh)
    out["cost_usd_all_calls"] = round(sum(cost(model, c["usage"] or {}) for c in calls), 4)
    out["cost_usd_this_run"] = round(sum(cost(model, c["usage"] or {}) for c in fresh), 4)
    out["cache"] = {"hit_rate": {"k": sum(1 for c in fresh if ((c["usage"] or {}).get("cache_read_input_tokens") or 0) > 0), "n": len(fresh)},
                    "cost_split": cost_split(model, usage_sum(fresh), summed=True), "prefix_hashes": sorted({c["prefix_hash"] for c in calls if c.get("prefix_hash")})}
    out["deadline_expiries"] = sum(len(r.get("deadline_expiries") or []) for r in rows)
    out["samples_retried_after_expiry"] = [r["seed"] for r in rows if r.get("deadline_expiries")]
    return out


def _csv_value(stage: dict) -> str:
    """results.csv cell value: final mirror_sufficient as 1/0; NA when the policy is invalid (or could not be replayed)."""
    return "NA" if not stage["scored"] else ("1" if stage["mirror_sufficient"] else "0")


def write_results_csv(path: Path, model: str, cells: list[str], rows: list[dict]) -> None:
    by = {(r["cell"], r["seed"]): r for r in rows}
    seeds = sorted({r["seed"] for r in rows})
    cols = ["model", "seed"] + [f"{c}{suffix}" for c in cells for suffix in ("", ".first_shot", ".declined", ".form", ".valid", ".rounds")]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for seed in seeds:
            line = [model, seed]
            for c in cells:
                r = by.get((c, seed))
                if r is None:
                    line += [""] * 6
                else:
                    line += [_csv_value(r["final"]), _csv_value(r["first_shot"]), int(r["final"]["declined"]), r["final"]["form"],
                             int(r["final"]["valid"]), r["rounds"]]
            w.writerow(line)


def write_samples_csv(path: Path, model: str, rows: list[dict]) -> None:
    cols = ["model", "cell", "seed", "level", "variant", "decline", "stage", "valid", "scored", "mirror_sufficient", "exact", "silent_reads_mirror",
            "silent_all_allow", "workflow_deficit", "admitted", "declined", "form", "form_by_order", "rounds", "surplus", "deficit",
            "truncated_rounds", "final_truncated"]
    fmt = lambda v: "" if v is None else (int(v) if isinstance(v, bool) else ";".join(v) if isinstance(v, list) else v)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            for stage in STAGES:
                s = r[stage]
                w.writerow([model, r["cell"], r["seed"], r["level"], r["variant"], int(r["decline"]), stage, int(s["valid"]), int(s["scored"]),
                            fmt(s["mirror_sufficient"]), fmt(s["exact"]), fmt(s["silent_reads_mirror"]), fmt(s["silent_all_allow"]),
                            fmt(s["workflow_deficit"]), int(s["admission"]["admitted"]), int(s["declined"]), s["form"], s["form_by_order"],
                            r["rounds"], fmt(s["surplus"]), fmt(s["deficit"]), ";".join(map(str, r["truncated_rounds"])), int(r["final_truncated"])])


def _pct(r: dict) -> str:
    return f"{r['k']}/{r['n']}" + (f" (≤{100 * r['upper95']:.1f}%, ≥{100 * r['lower95']:.1f}%)" if r["n"] else "")


def markdown(config: dict, summary: dict, instances: list[dict]) -> str:
    cells = list(summary)
    lines = [f"# E1 instance run {config['run_id']}", "",
             f"Model `{config['model']}`; cells {', '.join(cells)}; seeds {config['seeds']}; generator {config['generator']['generator']} "
             f"(max {config['generator']['max_rounds']} rounds, no judge); layout {config['generator']['layout']}; one cached prefix "
             f"`{config['request']['prompt_cache']['prefix_hash'][:12]}`. Oracle: Dogwood replay over each instance's 19-trace suite against the "
             "instance's own roles. Surrogate evidence about the pattern, not about AgentCore. Rates are k/n over scored samples (valid and "
             "replayed) with exact one-sided 95% bounds (upper, lower); D0 cells are baselines and controls, never violations.", ""]
    lines += ["## Cells", "", "| cell | level | variant | decline | planned n | run |", "|---|---|---|---|---|---|"]
    for c in cells:
        cc = config["cells"][c]
        lines.append(f"| {c} | {cc['level']} | {cc['variant']} | {cc['decline']} | {cc['n']} | {summary[c]['n']} |")
    for stage, title in (("final", "Final policies (after the validator loop)"), ("first_shot", "First shots (round 1)")):
        lines += ["", f"## {title}", "",
                  "| cell | valid | scored | mirror_sufficient | exact | silent (reads_mirror) | silent (all ALLOW) | workflow deficit direct / reads_mirror / mirror_negative | admitted (of valid) | declined | forms |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for c in cells:
            s = summary[c][stage]
            wd = s["workflow_deficit"]
            forms = ", ".join(f"{k} {v}" for k, v in s["forms"].items() if v)
            lines.append(f"| {c} | {s['valid']['k']}/{s['valid']['n']} | {s['scored']} | {_pct(s['mirror_sufficient'])} | {_pct(s['exact'])} "
                         f"| {s['silent_reads_mirror']['k']}/{s['scored']} | {s['silent_all_allow']['k']}/{s['scored']} "
                         f"| {wd.get('direct', 0)} / {wd.get('reads_mirror', 0)} / {wd.get('mirror_negative', 0)} | {s['admitted']['k']}/{s['admitted']['n']} "
                         f"| {s['declined']['k']}/{s['declined']['n']} | {forms or '—'} |")
    lines += ["", f"## Rounds, stop reasons (max_tokens = {config['request']['max_tokens']}), cache and spend", "",
              "| cell | rounds used | stop reasons | max_tokens stops | samples truncated (final) | api calls | cache hits | cost this run $ | expiries |", "|---|---|---|---|---|---|---|---|---|"]
    for c in cells:
        s = summary[c]
        lines.append(f"| {c} | {s['rounds']} | {s['stop_reasons']} | {s['max_tokens_stops']} | {len(s['samples_truncated'])} ({len(s['samples_final_truncated'])}) "
                     f"| {s['api_calls']} | {s['cache']['hit_rate']['k']}/{s['cache']['hit_rate']['n']} | {s['cost_usd_this_run']:.3f} | {s['deadline_expiries']} |")
    lines += ["", "## Instances", "", "| seed | designated | mirror | vocabulary | paraphrase | schema order (designated is) |", "|---|---|---|---|---|---|"]
    for i in instances:
        lines.append(f"| {i['seed']} | {i['auth']} | {i['mirror']} | {i['vocab']} | {i['paraphrase']} | {i['designated_position']} |")
    lines += ["", f"Deadline {config['request']['deadline']['seconds']} s per call, {config['request']['deadline']['retries_on_expiry']} retries on expiry; a sample "
                  "that succeeded after an expiry is a normal sample. Binding forms are text, descriptive only. results.csv: per cell the final "
                  "mirror_sufficient (1/0; NA only when the final policy is invalid or not replayable)."]
    return "\n".join(lines) + "\n"


# ---- main
def main(argv: list[str] | None = None) -> Path | None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--model", required=True)
    p.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO, help="scenario folder holding cells.yaml, the builder and the lock")
    p.add_argument("--cells", nargs="+", required=True)
    p.add_argument("--seeds", nargs="+", required=True, help="lock-pinned instance seeds; `0-59` is an inclusive range")
    p.add_argument("--label", default="")
    p.add_argument("--spend-cap-usd", type=float)
    p.add_argument("--cache-only", action="store_true")
    p.add_argument("--cache", type=Path, default=ROOT / "cache/llm")
    p.add_argument("--runs-dir", type=Path, default=ROOT / "runs")
    p.add_argument("--deadline-s", type=float, default=DEFAULT_DEADLINE_S)
    p.add_argument("--max-rounds", type=int, default=3)
    p.add_argument("--effort", default="high")
    p.add_argument("--max-tokens", type=int, default=16000, help="output cap per call (recorded in config); Haiku runs use 32000 (decision 2026-11-22), Sonnet 16000")
    args = p.parse_args(argv)

    spec = load_cells(args.scenario / "cells.yaml")
    if unknown := [c for c in args.cells if c not in spec.cells]:
        raise SystemExit(f"unknown cells {unknown}; cells.yaml has {sorted(spec.cells)}")
    cells = [spec.cells[c] for c in args.cells]
    seeds = parse_seeds(args.seeds)
    builder = load_builder(args.scenario, spec.builder)
    registry = sys.modules["registry"].REGISTRY if "registry" in sys.modules else __import__("registry").REGISTRY
    lock = json.loads(builder.LOCK.read_text())
    lock_sha = hashlib.sha256(builder.LOCK.read_bytes()).hexdigest()
    for c in cells:
        if len(seeds) > c.n:
            raise SystemExit(f"cell {c.name}: {len(seeds)} seeds exceed its planned n = {c.n}")

    # instances: render or verify against the lock; roles and the instance table
    instances: dict[tuple[int, str], dict] = {}
    for c in cells:
        for seed in seeds:
            if (seed, c.variant) in instances:
                continue
            folder, tree = builder.ensure_instance(seed, c.variant, lock, args.scenario / "instances")
            rec = json.loads((folder / "instance.json").read_text())
            instances[(seed, c.variant)] = {"folder": folder, "tree_sha256": tree, "record": rec, "roles": roles_of(rec)}
    table = []
    for seed in seeds:
        rec = next(v["record"] for (s, _), v in instances.items() if s == seed)
        roles = roles_of(rec)
        table.append({"seed": seed, "auth": rec["draw"]["auth"], "mirror": rec["draw"]["mirror"], "vocab": rec["draw"]["vocab"],
                      "paraphrase": rec["draw"]["paraphrase"], "vocabulary": rec["vocabulary"], **roles,
                      "variants": {v: {"id": inst["record"]["id"], "tree_sha256": inst["tree_sha256"], "actions": inst["record"]["actions"]}
                                   for (s, v), inst in sorted(instances.items()) if s == seed}})

    # trusted precheck and the one prefix, before any call
    cfgs = {c.name: dogwood.ValidatorLoopConfig(args.model, max_rounds=args.max_rounds, effort=args.effort, max_tokens=args.max_tokens,
                                                 contract_block=c.level in spec.contract_block_levels, decline=c.decline) for c in cells}
    loaded: dict[tuple[str, int], DogwoodInputs] = {}
    prechecks: dict[str, dict] = {}
    hashes: dict[str, str] = {}
    first_params = None
    for c in cells:
        prechecks[c.name] = {}
        for seed in seeds:
            inp = load_dogwood_inputs(instances[(seed, c.variant)]["folder"], intent=c.level)
            loaded[(c.name, seed)] = inp
            pc = precheck(inp, c, spec, registry)
            prechecks[c.name][str(seed)] = pc
            if not pc["ok"]:
                raise ResolverPrecheckFailed(f"cell {c.name} ({c.level}/{c.variant}) seed {seed}: {pc['why']}; nothing sent")
            msgs, params = dogwood.build_request(inp, cfgs[c.name].naive())
            hashes[f"{c.name}:{seed}"] = prefix_hash(args.model, params)
            first_params = first_params or params
    if len(set(hashes.values())) != 1:
        raise PrefixNotShared(f"the samples would use {len(set(hashes.values()))} different prefixes: {hashes}; nothing sent")
    (h,) = set(hashes.values())

    from pgi.llm.anthropic_provider import AnthropicProvider
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = "-".join(x for x in (stamp, "e1-instances", args.label) if x)
    with atomic_run_dir(args.runs_dir, run_id) as out:
        watch = None
        if args.cache_only:
            provider, transport = _NoProvider(), None
            telemetry = {"enabled": False, "reason": "cache-only run: no API call, nothing to observe"}
        else:
            provider = DeadlineProvider(AnthropicProvider(), seconds=args.deadline_s)
            transport = provider.request_settings()
            watch = PrefixWatch(expected={"generation": h}, model=args.model)
            provider = _Budget(provider, args.model, args.spend_cap_usd, watch)
            telemetry = {"enabled": watch.enabled, "reason": watch.disabled_reason}
        llm = CachedLLM(provider, args.cache, allow_api=not args.cache_only)
        deadline_s = None if args.cache_only else args.deadline_s
        config = {"run_id": run_id, "created": stamp, "kind": "e1-instances", "model": args.model, "cells": {c.name: asdict(c) for c in cells},
                  "seeds": seeds, "scenario": str(args.scenario), "cells_yaml_sha256": spec.sha256, "lock_sha256": lock_sha,
                  "builder": {"file": spec.builder, "sha256": hashlib.sha256((args.scenario / spec.builder).read_bytes()).hexdigest(),
                              "pydogwood_in_lock": lock.get("pydogwood")},
                  "instances": {f"{s}:{v}": {"id": i["record"]["id"], "tree_sha256": i["tree_sha256"]} for (s, v), i in sorted(instances.items())},
                  "generator": cfgs[cells[0].name].as_dict() | {"per_cell": {c.name: {"contract_block": cfgs[c.name].contract_block, "decline": cfgs[c.name].decline} for c in cells}},
                  "cache_only": args.cache_only, "spend_cap_usd": args.spend_cap_usd,
                  "request": {"sampling": "not sent (API default)", "thinking": {"type": "adaptive"}, "output_config": {"effort": args.effort},
                              "max_tokens": args.max_tokens, "final_line": {"plain": dogwood.FINAL_LINE, "decline": dogwood.FINAL_LINE_DECLINE},
                              "prompt_cache": {"layout": "split", "breakpoint": "ephemeral breakpoint on block 4 (action schema part 1 = prompt_schema_base)",
                                               "prefix_hash": h, "telemetry": telemetry, "run_level_prefix_rule": "on" if watch else "off (cache-only run)",
                                               "circuit_breaker": "3 consecutive zero-read fresh calls on a written prefix stop the run" if watch else None},
                              "transport": transport,
                              "deadline": {"seconds": deadline_s, "retries_on_expiry": DEFAULT_MAX_RETRIES,
                                           "rule": "a sample whose call expires is retried with the same request up to twice; after the third expiry the run stops; "
                                                   "a sample that succeeded after one or two expiries is a normal sample; a late result is never cached"}},
                  "resolver_precheck": prechecks, "registry_sha256": registry.sha256(),
                  "scoring": {"roles": "the instance's own (draw); D0 cells are baselines and controls", "primary": "mirror_sufficient (final)",
                              "bounds": "exact one-sided 95% over scored samples", "binding_form": "text, descriptive only (dogwood_text.binding_form)"},
                  "versions": _versions()}
        _dump(out / "config.json", config)
        _dump(out / "prompt_prefix.json", {"prefix_hash": h, "blocks": prefix_blocks(first_params)})
        _dump(out / "instances.json", table)
        rows: list[dict] = []
        events: list[dict] = []
        try:
            for c in cells:
                for seed in seeds:
                    inp = loaded[(c.name, seed)]
                    fr = frame(inp)
                    d = out / c.name / f"seed_{seed}"
                    roles = instances[(seed, c.variant)]["roles"]

                    def one(attempt: int, inp=inp, fr=fr, c=c, seed=seed, d=d, roles=roles) -> dict:
                        return run_one(llm, inp, fr, cfgs[c.name], c, seed, d, roles, deadline_s, attempt - 1)
                    try:
                        row, ev = run_sample_with_retries(one, generator=c.name, sample=seed)
                    except DeadlineRunStopped as e:
                        events += e.events
                        raise
                    events += ev
                    row["deadline_expiries"] = ev
                    if ev:
                        _dump(d / "deadline.json", ev)
                    rows.append(row)
                    f = row["final"]
                    print(f"{c.name} seed {seed}: rounds={row['rounds']} valid={f['valid']} mirror_sufficient={f['mirror_sufficient']} exact={f['exact']} "
                          f"form={f['form']} declined={f['declined']} admitted={f['admission']['admitted']}", flush=True)
        finally:
            _dump(out / "deadline_events.json", events)
            if isinstance(provider, _Budget):
                _dump(out / "spend.json", provider.spend() | {"cap_usd": provider.cap_usd})
            if watch is not None:
                _dump(out / "cache_watch.json", watch.summary())
        workflows = list(frame(loaded[(cells[0].name, seeds[0])]).requirements.workflows)
        summary = {c.name: summarize_cell(args.model, [r for r in rows if r["cell"] == c.name], workflows) for c in cells}
        _dump(out / "summary.json", summary)
        write_results_csv(out / "results.csv", args.model, [c.name for c in cells], rows)
        write_samples_csv(out / "samples.csv", args.model, rows)
        (out / "summary.md").write_text(markdown(config, summary, table))
    final = args.runs_dir / run_id
    spent = ""
    if isinstance(provider, _Budget):
        spent = f"; spent ${provider.spent_usd:.4f}" + (f" of cap ${provider.cap_usd:.2f}" if provider.cap_usd is not None else "")
        if watch is not None and watch.enabled:
            hr = watch.summary()["hit_rate"]
            spent += f"; cache hits {hr['k']}/{hr['n']} fresh calls"
    print(f"\nwrote {final}\napi calls this run: {llm.api_calls}{spent}")
    return final


if __name__ == "__main__":
    main()
