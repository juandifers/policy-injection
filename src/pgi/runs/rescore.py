"""Re-score every sample of a run folder from the run's own input snapshot. No LLM, no writes.

    uv run python -m pgi.runs.rescore runs/<id> [--inputs-root DIR]

Inputs come from <run>/inputs/<scenario>/ (or --inputs-root/<scenario>/ for runs that predate
snapshots), never from the live scenario files. Prints the sample keys whose record differs from the
stored oracle.json, ignoring the file paths a record names.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pgi.runs.judge import score
from pgi.runs.snapshot import load_snapshot


def rescore(run_dir: Path, inputs_root: Path | None = None) -> dict[str, dict]:
    """{"<scenario>/<generator>/<sample>": oracle record} for every sample with a policy.cedar."""
    run_dir = Path(run_dir)
    inputs_root = Path(inputs_root) if inputs_root else run_dir / "inputs"
    out = {}
    for scen in sorted(p for p in inputs_root.iterdir() if p.is_dir()):
        inputs = load_snapshot(scen)
        for policy in sorted((run_dir / inputs.name).glob("*/sample_*/policy.cedar")):
            out[str(policy.parent.relative_to(run_dir))] = score(policy, inputs)
    return out


def _paths_removed(rec: dict) -> dict:
    rec = json.loads(json.dumps(rec))
    rec.pop("critic", None)
    rec.pop("cause_tags", None)
    for k in ("policy", "schema"):
        rec["validation"].pop(k, None)
    return rec


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("run", type=Path)
    p.add_argument("--inputs-root", type=Path)
    args = p.parse_args()
    records = rescore(args.run, args.inputs_root)
    diff = [k for k, r in records.items()
            if _paths_removed(r) != _paths_removed(json.loads((args.run / k / "oracle.json").read_text()))]
    print(f"{len(records)} samples re-scored; {len(diff)} differ from the stored records")
    for k in diff:
        print("  differs:", k)


if __name__ == "__main__":
    main()
