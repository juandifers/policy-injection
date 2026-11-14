"""Compare a clean run with a mutated (probe or attack) run, case by case. No LLM.

    uv run python -m pgi.runs.compare CLEAN_RUN MUTATED_RUN [--fisher CASE ...]

Both runs must have scored each shared scenario against the same reference and universe (hashes in
config.json), so allow counts are comparable. Per scenario x generator: k/n in both runs for every
case (n = valid samples), a one-sided Fisher exact test per named case (H1: the case is allowed less
often in the mutated run), the default-reliance counts of both runs, and final-policy comment lines
that mention a default.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pgi.analysis.stats import fisher_less

_DEFAULT = re.compile(r"\bdefault", re.IGNORECASE)


def _load(run: Path) -> tuple[dict, dict]:
    return json.loads((run / "config.json").read_text()), json.loads((run / "summary.json").read_text())


def comments_mentioning_default(run: Path) -> dict:
    """{scenario: {generator: {samples: [i], lines: [{sample, line}]}}} over final policy.cedar comments."""
    out: dict = {}
    for policy in sorted(Path(run).glob("*/*/sample_*/policy.cedar")):
        sample, gen, scen = policy.parent.name, policy.parent.parent.name, policy.parent.parent.parent.name
        i = int(sample.split("_")[1])
        entry = out.setdefault(scen, {}).setdefault(gen, {"samples": [], "lines": []})
        for line in policy.read_text().splitlines():
            comment = line[line.index("//"):] if "//" in line else ""
            if comment and _DEFAULT.search(comment):
                entry["lines"].append({"sample": i, "line": comment.strip()})
                if i not in entry["samples"]:
                    entry["samples"].append(i)
    return out


def compare(clean: Path, mutated: Path, fisher_cases: list[str]) -> dict:
    ccfg, csum = _load(Path(clean))
    mcfg, msum = _load(Path(mutated))
    cmt_c, cmt_m = comments_mentioning_default(Path(clean)), comments_mentioning_default(Path(mutated))
    out: dict = {}
    for key in sorted(set(csum) & set(msum)):
        scen, gen = key.split("/")
        for h in ("reference", "universe"):
            a, b = ccfg["scenarios"][scen]["hashes"][h], mcfg["scenarios"][scen]["hashes"][h]
            if a != b:
                raise ValueError(f"{scen}: {h} differs between the runs ({a[:12]} vs {b[:12]}); counts are not comparable")
        c, m = csum[key], msum[key]
        ref = set(c.get("reference_allow_set") or [])
        cases = {case: {"clean": f"{cc['k']}/{cc['n']}", "probe": f"{m['allow_counts'][case]['k']}/{m['allow_counts'][case]['n']}",
                        "reference": "allow" if case in ref else "deny"}
                 for case, cc in c["allow_counts"].items()}
        fisher = {}
        for case in fisher_cases:
            a, b = c["allow_counts"][case], m["allow_counts"][case]
            fisher[case] = fisher_less(a["k"], a["n"], b["k"], b["n"]) if a["n"] and b["n"] else None
        dc, dm = c["default_reliance"], m["default_reliance"]
        empty = {"samples": [], "lines": []}
        out.setdefault(scen, {})[gen] = {
            "valid": {"clean": f"{c['valid']}/{c['n']}", "probe": f"{m['valid']}/{m['n']}"},
            "cases": cases, "fisher_less": fisher,
            "default_reliance": {"clean": f"{dc['samples_relying']}/{dc['samples_checked']}",
                                 "probe": f"{dm['samples_relying']}/{dm['samples_checked']}",
                                 "clean_by_field": dc["samples_by_field"], "probe_by_field": dm["samples_by_field"]},
            "comments_mentioning_default": {"clean": cmt_c.get(scen, {}).get(gen, empty),
                                            "probe": cmt_m.get(scen, {}).get(gen, empty)}}
    return out


def markdown(result: dict, clean_id: str, mutated_id: str) -> str:
    lines = [f"# Comparison: clean `{clean_id}` vs mutated `{mutated_id}`", ""]
    for scen, gens in result.items():
        names = list(gens)
        lines += [f"## {scen}", "", "| case | P_ref | " + " | ".join(f"{g} clean | {g} mutated" for g in names) + " |",
                  "|---|---|" + "---|---|" * len(names)]
        for case in gens[names[0]]["cases"]:
            cells = " | ".join(f"{gens[g]['cases'][case]['clean']} | {gens[g]['cases'][case]['probe']}" for g in names)
            lines.append(f"| {case} | {gens[names[0]]['cases'][case]['reference']} | {cells} |")
        lines += ["", "k/n = valid samples allowing the case / valid samples (enumeration).", ""]
        for g in names:
            r = gens[g]
            fis = ", ".join(f"{c}: {'n/a (no valid samples)' if p is None else f'{p:.3g}'}" for c, p in r["fisher_less"].items())
            d = r["default_reliance"]
            cm = r["comments_mentioning_default"]
            lines += [f"- **{g}**: valid {r['valid']['clean']} → {r['valid']['probe']}. "
                      f"One-sided Fisher (allowed less often when mutated): {fis or '—'}. "
                      f"Relies on a default: {d['clean']} → {d['probe']}. "
                      f"Final policies with a comment mentioning a default: {len(cm['clean']['samples'])} → {len(cm['probe']['samples'])}."]
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("clean", type=Path)
    p.add_argument("mutated", type=Path)
    p.add_argument("--fisher", nargs="*", default=[])
    args = p.parse_args()
    res = compare(args.clean, args.mutated, args.fisher)
    print(json.dumps(res, indent=1))
    print(markdown(res, args.clean.name, args.mutated.name))


if __name__ == "__main__":
    main()
