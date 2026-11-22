"""E1 comparison over results.csv files (Phase 3, 2026-11-22). Zero API; reads only.

    uv run python -m pgi.runs.e1_compare runs/<id>/results.csv [runs/<id2>/results.csv ...] [--cells domains/.../cells.yaml]

Rows are merged by (model, seed); a cell column present in two files with different values is an error (the same sample
cannot have two outcomes). Per model it prints:
- the contrast families of cells.yaml (`contrasts`): for each pair (A, B) the discordant counts b (A = 1, B = 0) and c (A = 0,
  B = 1) over seeds where both cells are scored (neither NA), the exact two-sided McNemar p, and Holm within the family;
- one table per family of cells.yaml (`families`): boundary crossings, guesses under underspecification, controls. The tables
  are never merged: a D0 cell is a baseline or a control, not a violation.
Per cell: final mirror_sufficient k/n over scored samples with the exact one-sided 95% upper bound, first-shot k/n, declined
k/n over all samples of the cell, and the distribution of binding forms (text, descriptive only).
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from pgi.analysis.stats import binomial_upper, holm, mcnemar_exact
from pgi.runs.temporal_instances import DEFAULT_SCENARIO, load_cells


class ConflictingResults(ValueError):
    """The same (model, seed, cell) has two different values across the files."""


def read_results(paths: list[Path]) -> dict[tuple[str, int], dict[str, str]]:
    """(model, seed) -> {column: value}, merged across files; empty strings are 'not run' and never conflict."""
    rows: dict[tuple[str, int], dict[str, str]] = {}
    for path in paths:
        with open(path, newline="") as f:
            for rec in csv.DictReader(f):
                key = (rec["model"], int(rec["seed"]))
                cur = rows.setdefault(key, {})
                for col, val in rec.items():
                    if col in ("model", "seed") or val == "":
                        continue
                    if col in cur and cur[col] != val:
                        raise ConflictingResults(f"{path}: {key} column {col}: {val!r} conflicts with {cur[col]!r} read earlier")
                    cur[col] = val
    return rows


def _scored(rows: dict, model: str, cell: str) -> dict[int, int]:
    """seed -> 0/1 for the scored samples of one cell (NA and not-run excluded)."""
    return {seed: int(v) for (m, seed), r in rows.items() if m == model and (v := r.get(cell)) not in (None, "NA")}


def contrast(rows: dict, model: str, a: str, b: str) -> dict:
    sa, sb = _scored(rows, model, a), _scored(rows, model, b)
    both = sorted(set(sa) & set(sb))
    disc_a = sum(1 for s in both if sa[s] == 1 and sb[s] == 0)
    disc_b = sum(1 for s in both if sa[s] == 0 and sb[s] == 1)
    return {"a": a, "b": b, "pairs": len(both), "a_only": disc_a, "b_only": disc_b, "both": sum(1 for s in both if sa[s] == sb[s] == 1),
            "p": mcnemar_exact(disc_a, disc_b)}


def cell_row(rows: dict, model: str, cell: str) -> dict:
    final = _scored(rows, model, cell)
    first = _scored(rows, model, f"{cell}.first_shot")
    ran = {seed: r for (m, seed), r in rows.items() if m == model and r.get(cell) is not None}
    declined = sum(1 for r in ran.values() if r.get(f"{cell}.declined") == "1")
    forms = Counter(r.get(f"{cell}.form", "") for r in ran.values())
    k, n = sum(final.values()), len(final)
    return {"cell": cell, "n": len(ran), "scored": n, "mirror_sufficient": k, "upper95": binomial_upper(k, n) if n else None,
            "first_shot_scored": len(first), "first_shot_mirror_sufficient": sum(first.values()),
            "declined": declined, "forms": dict(sorted(forms.items())), "invalid_final": sum(1 for r in ran.values() if r.get(cell) == "NA")}


def report(rows: dict, spec) -> dict:
    models = sorted({m for m, _ in rows})
    out = {}
    for model in models:
        fam = {}
        for name, pairs in spec.contrasts.items():
            cs = {f"{a} vs {b}": contrast(rows, model, a, b) for a, b in pairs}
            adj = holm({k: v["p"] for k, v in cs.items()})
            fam[name] = {k: v | {"holm_adjusted": adj[k]["adjusted"], "reject_05": adj[k]["reject"]} for k, v in cs.items()}
        tables = {name: [cell_row(rows, model, c) for c in cells] for name, cells in spec.families.items()}
        out[model] = {"contrasts": fam, "tables": tables}
    return out


def markdown(rep: dict) -> str:
    lines = ["# E1 comparison", "", "Final mirror_sufficient per cell (1/0 per seed; NA when the final policy is invalid). McNemar: exact two-sided on the "
             "discordant pairs over seeds scored in both cells; Holm within each family. The three tables are never merged: D0 cells are "
             "baselines and controls, never violations.", ""]
    for model, r in rep.items():
        lines += [f"## {model}", ""]
        for fam, cs in r["contrasts"].items():
            lines += [f"### Contrasts: {fam} (Holm over {len(cs)})", "", "| contrast | pairs | both | A only | B only | McNemar p | Holm adj. | reject at 0.05 |", "|---|---|---|---|---|---|---|---|"]
            for name, c in cs.items():
                lines.append(f"| {name} | {c['pairs']} | {c['both']} | {c['a_only']} | {c['b_only']} | {c['p']:.4g} | {c['holm_adjusted']:.4g} | {'yes' if c['reject_05'] else 'no'} |")
            lines.append("")
        titles = {"boundary": "Boundary crossings", "guesses": "Guesses under underspecification", "controls": "Controls"}
        for fam, table in r["tables"].items():
            lines += [f"### {titles.get(fam, fam)} ({fam})", "", "| cell | n | scored | mirror_sufficient (final) | upper 95% | first shot | declined | invalid final | forms |", "|---|---|---|---|---|---|---|---|---|"]
            for t in table:
                ub = f"{100 * t['upper95']:.1f}%" if t["upper95"] is not None else "—"
                forms = ", ".join(f"{k or '?'} {v}" for k, v in t["forms"].items())
                lines.append(f"| {t['cell']} | {t['n']} | {t['scored']} | {t['mirror_sufficient']}/{t['scored']} | {ub} | {t['first_shot_mirror_sufficient']}/{t['first_shot_scored']} "
                             f"| {t['declined']}/{t['n']} | {t['invalid_final']} | {forms or '—'} |")
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> dict:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("results", nargs="+", type=Path, help="results.csv files (or run folders containing one)")
    p.add_argument("--cells", type=Path, default=DEFAULT_SCENARIO / "cells.yaml")
    p.add_argument("--out", type=Path, help="also write the markdown here")
    args = p.parse_args(argv)
    paths = [q / "results.csv" if q.is_dir() else q for q in args.results]
    rep = report(read_results(paths), load_cells(args.cells))
    text = markdown(rep)
    print(text)
    if args.out:
        args.out.write_text(text)
    return rep


if __name__ == "__main__":
    main()
