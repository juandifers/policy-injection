"""Admission check over the final policies of temporal-clean runs (Phase 2c Part C; zero API calls).

    uv run --group dogwood python -m pgi.runs.admission_check --catalogue domains/.../admission.catalogue.yaml \\
        --label t01 runs/<id> runs/<id> ...

Writes runs/<stamp>-admission-<label>/report.json (per run, per generator, per sample: admitted / reasons next to the
recorded behaviour) and report.md (per arm: admitted, rejected by reason class, rejected policies that allow a vendor-only
trace, admitted policies that are not exact-gold, exact-gold policies that are rejected). The checker is
pgi.analysis.admission: deterministic, text-only, fail closed, no LLM. Same atomic folder rule as every run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from pgi.analysis.admission import check_run, load_catalogue, summarize_check
from pgi.runs.clean import _dump, atomic_run_dir

ROOT = Path(__file__).resolve().parents[3]


def markdown(report: dict) -> str:
    lines = [f"# Admission check {report['run_id']}", "",
             f"Catalogue `{report['catalogue']}` (sha256 `{report['catalogue_sha256'][:12]}…`), checker `pgi.analysis.admission` "
             f"(deterministic, text only, fail closed; no LLM). Final policies of {len(report['runs'])} runs. Behaviour columns "
             "(valid, exact, allows vendor-only) are the runs' recorded oracle results; the verdict is text.", "",
             "| arm | input mode | generator | admitted | rejected | vacuous | rejected by reason class | rejected ∧ allows vendor-only | admitted ∧ allows vendor-only | admitted ∧ not exact-gold | exact-gold ∧ rejected | admitted ∧ invalid |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in report["runs"]:
        for gen, s in r["summary"].items():
            fmt = lambda xs: f"{len(xs)}" + (f" {xs}" if xs else "")
            lines.append(f"| {r['arm']} | {r['input_mode']} | {gen} | {s['admitted']}/{s['n']} | {s['rejected']}/{s['n']} | {s['vacuous']} | {s['reason_classes']} "
                         f"| {fmt(s['rejected_allowing_vendor_only'])} | {fmt(s['admitted_allowing_vendor_only'])} | {fmt(s['admitted_not_exact'])} "
                         f"| {fmt(s['exact_rejected'])} | {fmt(s['admitted_invalid'])} |")
    lines += ["", "Lists are sample indices. Runs: " + ", ".join(f"{r['arm']} `{r['source_run']}`" for r in report["runs"]) + "."]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--catalogue", type=Path, required=True)
    p.add_argument("--label", default="")
    p.add_argument("runs", nargs="+", type=Path)
    args = p.parse_args()
    cat = load_catalogue(args.catalogue)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = "-".join(x for x in (stamp, "admission", args.label) if x)
    with atomic_run_dir(ROOT / "runs", run_id) as out:
        runs = []
        for r in args.runs:
            rep = check_run(r, cat)
            rep["source_run"] = r.name
            rep["source_config_sha256"] = hashlib.sha256((r / "config.json").read_bytes()).hexdigest()
            rep["summary"] = summarize_check(rep)
            runs.append(rep)
        report = {"run_id": run_id, "created": stamp, "kind": "admission", "catalogue": str(args.catalogue),
                  "catalogue_sha256": hashlib.sha256(args.catalogue.read_bytes()).hexdigest(), "catalogue_content": cat,
                  "git_commit": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
                  "runs": runs}
        _dump(out / "report.json", report)
        (out / "report.md").write_text(markdown(report))
    print(f"wrote {ROOT / 'runs' / run_id}")
    for r in runs:
        for gen, s in r["summary"].items():
            print(f"{r['arm']:6} {r['input_mode']:11} {gen:8} admitted {s['admitted']}/{s['n']} rejected {s['rejected']} {s['reason_classes']} "
                  f"rejected∧vendor-only {len(s['rejected_allowing_vendor_only'])} admitted∧¬exact {s['admitted_not_exact']} exact∧rejected {s['exact_rejected']}")


if __name__ == "__main__":
    main()
