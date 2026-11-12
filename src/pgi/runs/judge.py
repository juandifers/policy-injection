"""Score one generated policy against its scenario's reference with both oracle backends. No LLM here.

- strict validity (invalid policies get no allow-set and no symbolic result)
- enumeration: allow-set, surplus and deficit (case ids)
- symcc (with the R1/R2 exclusion): does P imply P_ref, per action; each realizable counterexample is
  replayed in cedarpy against the ORIGINAL P and P_ref
- blind spots: actions where symcc finds a realizable surplus but enumeration has no surplus case
"""

from __future__ import annotations

from pathlib import Path

from pgi.generators.inputs import ScenarioInputs
from pgi.oracle import realizable, validation
from pgi.oracle.enumeration import Universe, allowed, load_universe


def _uid(action: dict) -> str:
    """Cedar UID string of a request's action dict."""
    return f'{action["type"]}::"{action["id"]}"'


def score(policy: Path, inputs: ScenarioInputs) -> dict:
    """The full oracle record for one policy file."""
    report = validation.check(policy, inputs.schema_path)
    out: dict = {"validation": report.as_dict(), "valid": report.ok}
    if not report.ok:
        return out
    universe = load_universe(inputs.universe)
    ref_allow = allowed(inputs.reference, universe, inputs.schema_path)
    allow = allowed(policy, universe, inputs.schema_path)
    surplus, deficit = sorted(allow - ref_allow), sorted(ref_allow - allow)
    out["enumeration"] = {"allow_set": sorted(allow), "surplus": surplus, "deficit": deficit}
    surplus_actions = {_uid(universe.requests[c]["action"]) for c in surplus}
    symbolic, blind = [], []
    for env, c in realizable.implies(policy, inputs.reference, inputs.schema_path).items():
        row = {"action": env.action, "principal_type": env.principal_type, "resource_type": env.resource_type,
               "status": c.status, "violations": [v.__dict__ for v in c.violations], "counterexample": c.counterexample}
        if c.status == "does_not_hold":
            one = Universe({"cex": c.counterexample["request"]}, c.counterexample["entities"], {})
            row["replay_ok"] = (allowed(policy, one, inputs.schema_path) == {"cex"}
                                and allowed(inputs.reference, one, inputs.schema_path) == set())
            if env.action not in surplus_actions:
                row["blind_spot"] = True
                blind.append(env.action)
        symbolic.append(row)
    out["symbolic"] = {"implies_reference": all(r["status"] == "holds" for r in symbolic),
                       "per_action": symbolic, "blind_spots": blind,
                       "replay_failures": [r["action"] for r in symbolic if r.get("replay_ok") is False]}
    return out
