"""t01 adequacy check: gold vs contract on every trace; every weakening must differ from gold on >= 1 trace.

    uv run --group dogwood python domains/assetopsbench/scenarios/t01_close_after_approval/check.py

Deterministic (Dogwood reference interpreter via pgi.oracle.temporal); no LLM. Prints the decision matrix.
"""
from __future__ import annotations

from pathlib import Path

from pgi.oracle import temporal

D = Path(__file__).resolve().parent
SCHEMA = D / "schema" / "t01.dogwood.cedarschema"
EVENTS = D.parents[1] / "schema" / "agentcore.dwschema"  # AWS-shaped session pin


def main() -> None:
    suite = temporal.load_suite(D / "traces.yaml")
    gold = D / "gold.dw"
    weak = {p.stem.removeprefix("weak_"): p for p in sorted(D.glob("weak_*.dw"))}
    cols = list(suite.traces)
    rows = {name: {tid: temporal.decision(p, SCHEMA, t, EVENTS) for tid, t in suite.traces.items()}
            for name, p in [("gold", gold), *weak.items()]}
    print(f"{'policy':18s}" + "".join(f"{c.split('_')[0]:>5s}" for c in cols))
    print(f"{'contract':18s}" + "".join(f"{'A' if suite.contract[c] else 'd':>5s}" for c in cols))
    for name, row in rows.items():
        print(f"{name:18s}" + "".join(f"{'A' if row[c] else 'd':>5s}" for c in cols))
    report = temporal.adequacy(gold, weak, suite, SCHEMA, EVENTS)
    print("\ngold mismatches vs contract:", sorted(report.gold_mismatches))
    for name, traces in report.disagreements.items():
        print(f"  {name:17s} differs from gold on {sorted(traces)}")
    print("ADEQUATE:", report.adequate)


if __name__ == "__main__":
    main()
