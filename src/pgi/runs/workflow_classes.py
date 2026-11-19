"""Workflow classes of surplus policies over temporal-clean run folders (E0, 2026-11-20; zero API calls).

    uv run --group dogwood python -m pgi.runs.workflow_classes --label t01-e0 \\
        --surplus-traces t15_… t16_… t20_… t21_… --direct direct --reads-vendor reads_vendor runs/<id> runs/<id> ...

Per run (one arm), per view (first shot = the naive generator's samples; final = the Sondera-style generator's final
policies), over scored samples: SURPLUS = the sample allows any of `--surplus-traces`; a sample PASSES a workflow when its
recorded `workflows_allowed` (pgi.runs.temporal_clean.score, from the run's requirements.yaml `workflows`) names it. Each
surplus sample falls in exactly one class of the 2x2 (passes direct) x (passes reads_vendor):
    loud_in_both            passes neither
    silent_when_vendor_read fails direct, passes reads_vendor
    silent_in_both          passes both
    silent_direct_only      passes direct, fails reads_vendor (not expected; reported if it occurs)
Counts only. Reads oracle.json files; never replays, never calls an LLM. Writes runs/<stamp>-workflow-classes-<label>/
report.{json,md}; same atomic folder rule as every run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from pgi.runs.clean import _dump, atomic_run_dir

ROOT = Path(__file__).resolve().parents[3]
CLASSES = ("loud_in_both", "silent_when_vendor_read", "silent_in_both", "silent_direct_only")
VIEWS = {"first_shot": "naive", "final": "sondera"}


def classify(oracle: dict, surplus_traces: list[str], direct: str, reads_vendor: str) -> str | None:
    """The class of one scored sample with surplus, else None (invalid, unscored, or no surplus)."""
    if not oracle.get("valid") or not oracle.get("scored"):
        return None
    if not set(surplus_traces) & set(oracle["allow_set"]):
        return None
    passed = set(oracle.get("workflows_allowed", ()))
    d, v = direct in passed, reads_vendor in passed
    if d and v:
        return "silent_in_both"
    if v:
        return "silent_when_vendor_read"
    if d:
        return "silent_direct_only"
    return "loud_in_both"


def _samples(run: Path, scenario: str, gen: str) -> list[tuple[int, dict]]:
    out = []
    for d in sorted((run / scenario / gen).glob("sample_*")):
        out.append((int(d.name.split("_")[1]), json.loads((d / "oracle.json").read_text())))
    return out


def tally(run: Path, surplus_traces: list[str], direct: str, reads_vendor: str) -> dict:
    """Counts for one run folder, per view."""
    run = Path(run)
    config = json.loads((run / "config.json").read_text())
    scenario = config["scenario"]
    reqs = yaml.safe_load((run / "inputs" / scenario / "requirements.yaml").read_text())
    workflows = {k: list(v) for k, v in (reqs.get("workflows") or {}).items()}
    for w in (direct, reads_vendor):
        if w not in workflows:
            raise ValueError(f"{run}: requirements.yaml workflows has no {w!r} (has {sorted(workflows)})")
    report_traces = sorted(set(surplus_traces) | {t for ts in workflows.values() for t in ts})
    views = {}
    for view, gen in VIEWS.items():
        rows = _samples(run, scenario, gen)
        if not rows:
            continue
        scored = [(i, o) for i, o in rows if o.get("valid") and o.get("scored")]
        cls = {i: classify(o, surplus_traces, direct, reads_vendor) for i, o in scored}
        surplus = [i for i, c in cls.items() if c]
        views[view] = {"generator": gen, "n": len(rows), "scored": len(scored), "surplus": len(surplus), "surplus_samples": surplus,
                       "classes": {c: sum(1 for x in cls.values() if x == c) for c in CLASSES},
                       "class_samples": {c: [i for i, x in cls.items() if x == c] for c in CLASSES},
                       "workflow_pass_counts": {w: sum(w in o.get("workflows_allowed", ()) for _, o in scored) for w in workflows},
                       "allow_counts": {t: sum(t in o["allow_set"] for _, o in scored) for t in report_traces}}
    return {"arm": config.get("arm", {}).get("name", "base"), "input_mode": config.get("input_mode", "manifests"), "scenario": scenario,
            "source_run": run.name, "source_config_sha256": hashlib.sha256((run / "config.json").read_bytes()).hexdigest(),
            "cache_only": config.get("cache_only"), "workflows": workflows, "surplus_traces": list(surplus_traces), "views": views}


def markdown(report: dict) -> str:
    st = ", ".join(t.split("_")[0] for t in report["surplus_traces"])
    lines = [f"# Workflow classes {report['run_id']}", "",
             f"Surplus = allows any of {st}. Classes over scored samples with surplus, from (passes `{report['direct']}`) × "
             f"(passes `{report['reads_vendor']}`); a workflow is passed when every one of its traces is allowed. First shot = the "
             "naive generator's samples (= Sondera-style round 1); final = the Sondera-style final policies. Counts only; zero API.", "",
             "| arm | input mode | view | scored | surplus | loud in both | silent when vendor read | silent in both | silent direct only (unexpected) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in report["runs"]:
        for view, v in r["views"].items():
            c = v["classes"]
            lines.append(f"| {r['arm']} | {r['input_mode']} | {view.replace('_', ' ')} | {v['scored']} | {v['surplus']} | {c['loud_in_both']} "
                         f"| {c['silent_when_vendor_read']} | {c['silent_in_both']} | {c['silent_direct_only']} |")
    first = report["runs"][0]
    traces = next(iter(first["views"].values()))["allow_counts"]
    lines += ["", "## Allow counts (scored samples allowing the trace)", "",
              "| arm | input mode | view | scored | " + " | ".join(t.split("_")[0] for t in traces) + " |", "|---|---|---|---|" + "---|" * len(traces)]
    for r in report["runs"]:
        for view, v in r["views"].items():
            lines.append(f"| {r['arm']} | {r['input_mode']} | {view.replace('_', ' ')} | {v['scored']} | " + " | ".join(str(v["allow_counts"].get(t, "—")) for t in traces) + " |")
    lines += ["", "Runs: " + ", ".join(f"{r['arm']}{' (' + r['input_mode'] + ')' if r['input_mode'] != 'manifests' else ''} `{r['source_run']}`" for r in report["runs"]) + "."]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--surplus-traces", nargs="+", required=True)
    p.add_argument("--direct", required=True, help="name of the workflow without a vendor read (requirements.yaml `workflows`)")
    p.add_argument("--reads-vendor", required=True, help="name of the workflow with a positive vendor read")
    p.add_argument("--label", default="")
    p.add_argument("runs", nargs="+", type=Path)
    args = p.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = "-".join(x for x in (stamp, "workflow-classes", args.label) if x)
    with atomic_run_dir(ROOT / "runs", run_id) as out:
        runs = [tally(r, args.surplus_traces, args.direct, args.reads_vendor) for r in args.runs]
        report = {"run_id": run_id, "created": stamp, "kind": "workflow-classes", "surplus_traces": args.surplus_traces,
                  "direct": args.direct, "reads_vendor": args.reads_vendor,
                  "git_commit": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
                  "runs": runs}
        _dump(out / "report.json", report)
        (out / "report.md").write_text(markdown(report))
    print(f"wrote {ROOT / 'runs' / run_id}")
    for r in runs:
        for view, v in r["views"].items():
            print(f"{r['arm']:6} {r['input_mode']:11} {view:10} scored {v['scored']:2} surplus {v['surplus']:2} {v['classes']}")


if __name__ == "__main__":
    main()
