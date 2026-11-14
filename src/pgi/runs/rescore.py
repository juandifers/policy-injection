"""Re-score a run folder's stored policies. No LLM.

    uv run python -m pgi.runs.rescore runs/<id> [--inputs-root DIR]        # check: no writes
    uv run python -m pgi.runs.rescore runs/<id> --into --label L [--scenarios DIR ...]

Check mode: inputs come from <run>/inputs/<scenario>/ (or --inputs-root/<scenario>/ for runs that predate
snapshots), never from the live scenario files. Prints the sample keys whose record differs from the
stored oracle.json, ignoring the file paths a record names.

--into: scores the stored policies against the *current* scenario inputs (e.g. a revised reference) and
writes a new run folder runs/<stamp>-rescore-<L>/ with its own input snapshot. Generation is not re-run,
so no LLM is reachable: policies, round files and call records are copied from the source run, which is
only read. Oracle records, cause tags, provenance, default reliance and the summary are recomputed; the
Sondera-style critic record is copied (it describes the generation, not the scoring).
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pgi.generators.inputs import load_scenario_inputs
from pgi.runs.judge import score
from pgi.runs.snapshot import load_snapshot, snapshot

ROOT = Path(__file__).resolve().parents[3]
_RECOMPUTED = {"oracle.json", "provenance.json", "defaults.json"}


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


def _calls(sample: Path) -> list[dict]:
    """The source sample's call records, marked as cache hits: this run makes no call."""
    if (sample / "response.json").is_file():
        recs = [json.loads((sample / "response.json").read_text())]
        recs[0].pop("extraction", None)
    else:
        recs = []
        for r in sorted(sample.glob("round*.json"), key=lambda p: int(p.stem[5:])):
            rd = json.loads(r.read_text())
            recs += [c for c in (rd["generation"], rd["judge"]) if c]
    return [c | {"cache_hit": True} for c in recs]


def rescore_into(src_run: Path, scenarios: list[Path], runs_root: Path, label: str) -> Path:
    """Write runs_root/<stamp>-rescore-<label>/ scoring src_run's policies against the current inputs."""
    from pgi.runs import clean  # clean imports nothing from here; import late to keep the check mode light

    src_run = Path(src_run)
    src_cfg = json.loads((src_run / "config.json").read_text())
    for folder in scenarios:
        if not (src_run / Path(folder).name).is_dir():
            raise FileNotFoundError(f"{src_run} has no samples for {Path(folder).name}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-rescore-{label}"
    with clean.atomic_run_dir(Path(runs_root), run_id) as out:
        inputs = [snapshot(load_scenario_inputs(Path(f)), out / "inputs" / Path(f).name) for f in scenarios]
        config = {"run_id": run_id, "created": stamp, "kind": "rescore", "rescore_of": src_run.name,
                  "model": src_cfg["model"], "n": src_cfg["n"], "api_calls": 0,
                  "inputs": "inputs/<scenario>/ (snapshot of the current scenario files; scoring reads only from it)",
                  "policies": f"copied from {src_run.name}; generation was not re-run",
                  "calls": "the source run's call records, marked cache_hit; no LLM call was made",
                  "source_config": src_cfg,
                  "scenarios": {i.name: {"schema": str(i.schema_path.relative_to(out)), "servers": list(i.servers),
                                         "hashes": i.hashes} for i in inputs},
                  "versions": clean._tool_versions()}
        clean._dump(out / "config.json", config)
        results: dict[str, list[dict]] = {}
        for inp in inputs:
            for gen_dir in sorted(p for p in (src_run / inp.name).iterdir() if p.is_dir()):
                rows = []
                for old in sorted(gen_dir.glob("sample_*")):
                    new = out / inp.name / gen_dir.name / old.name
                    new.mkdir(parents=True)
                    for f in old.iterdir():
                        if f.is_file() and f.name not in _RECOMPUTED:
                            shutil.copy2(f, new / f.name)
                    oracle = score(new / "policy.cedar", inp)
                    crit = json.loads((old / "oracle.json").read_text()).get("critic")
                    tags = clean.cause_tags(new / "policy.cedar", inp, oracle)
                    clean._dump(new / "oracle.json", oracle | ({"critic": crit} if crit else {}) | {"cause_tags": tags})
                    prov = clean.literal_provenance(new / "policy.cedar", inp)
                    clean._dump(new / "provenance.json", prov)
                    rel = clean.default_reliance_rows(new / "policy.cedar", inp, oracle)
                    clean._dump(new / "defaults.json", rel)
                    row = {"sample": int(old.name.split("_")[1]), "calls": _calls(old), "oracle": oracle,
                           "cause_tags": tags, "provenance": prov, "default_reliance": rel}
                    rows.append(row | ({"critic": crit} if crit else {}))
                results[f"{inp.name}/{gen_dir.name}"] = rows
        cases = {}
        for inp in inputs:
            universe = clean.load_universe(inp.universe)
            cases[inp.name] = (list(universe.requests), sorted(clean.allowed(inp.reference, universe, inp.schema_path)))
        summary = {k: clean.summarize(config["model"], results[k], *cases[k.split("/")[0]]) for k in sorted(results)}
        clean._dump(out / "summary.json", summary)
        (out / "summary.md").write_text(clean.markdown(config, summary))
    return Path(runs_root) / run_id


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("run", type=Path)
    p.add_argument("--inputs-root", type=Path)
    p.add_argument("--into", action="store_true", help="write a new run folder scored against current inputs")
    p.add_argument("--label", default="")
    p.add_argument("--scenarios", nargs="+", type=Path)
    args = p.parse_args()
    if args.into:
        from pgi.runs.clean import DEFAULT_SCENARIOS
        if not args.label:
            p.error("--into needs --label")
        out = rescore_into(args.run, args.scenarios or DEFAULT_SCENARIOS, ROOT / "runs", args.label)
        print(f"wrote {out} (0 API calls)")
        return
    records = rescore(args.run, args.inputs_root)
    diff = [k for k, r in records.items()
            if _paths_removed(r) != _paths_removed(json.loads((args.run / k / "oracle.json").read_text()))]
    print(f"{len(records)} samples re-scored; {len(diff)} differ from the stored records")
    for k in diff:
        print("  differs:", k)


if __name__ == "__main__":
    main()
