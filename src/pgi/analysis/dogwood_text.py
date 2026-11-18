"""Text-level tally of what a Dogwood policy's temporal predicates name: actions, event kinds, bound fields, literals.

This is TEXT, not behaviour: it complements the behavioural scores of pgi.runs.temporal_clean (which decide
over-permissive / over-strict / source accepted) by saying *why* a sample behaved as it did, e.g. "bound the authority
response but guessed the value `APPROVED`". Never used as a score. Whole-token regexes over the policy text; a policy
the regexes misread is reported as-is, so counts here are a lower bound.

    uv run --group dogwood python -m pgi.analysis.dogwood_text runs/<id>   # tally per generator
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

_PREDICATE = re.compile(r'([A-Za-z_][\w:]*)::Action::"([^"]+)"::(request|response|error)\s*\{(.*?)\}', re.DOTALL)
_BINDING = re.compile(r'([A-Za-z_][\w.]*)\s*:\s*([A-Za-z_][\w]*(?:::[A-Za-z_]\w*)+::"[^"]*"|"[^"]*"|true|false|-?\d+(?:\.\d+)?|context\.[\w.]+|principal|resource|_|[A-Za-z_]\w*)')
_ENTITY_LITERAL = re.compile(r'^[A-Za-z_][\w]*(?:::[A-Za-z_]\w*)+::"([^"]*)"$')
_STRING_LITERAL = re.compile(r'^"([^"]*)"$')
_COMMENT = re.compile(r"//[^\n]*")
_SCOPE_ACTION = re.compile(r'\b(permit|forbid)\s*\(\s*principal[^,]*,\s*action\s*==\s*[\w:]*Action::"([^"]+)"')


def predicate_tally(text: str) -> dict:
    """Temporal predicates (action, kind, {field: pattern}) and the actions each permit/forbid is scoped to."""
    clean = _COMMENT.sub("", text)
    predicates = []
    for ns, action, kind, body in _PREDICATE.findall(clean):
        fields = {f: v for f, v in _BINDING.findall(body)}
        predicates.append({"action": action, "kind": kind, "fields": fields})
    scoped = [(eff, a) for eff, a in _SCOPE_ACTION.findall(clean)]
    return {"predicates": predicates,
            "permit_actions": sorted({a for e, a in scoped if e == "permit"}),
            "forbid_actions": sorted({a for e, a in scoped if e == "forbid"}),
            "literals": sorted({v for p in predicates for v in p["fields"].values() if v.startswith('"')})}  # string literals only; see literal_id


def literal_id(pattern: str) -> str | None:
    """The quoted value of a literal pattern: `"X"` -> X, `Ns::Type::"X"` (enum entity) -> X; anything else -> None."""
    if m := _ENTITY_LITERAL.match(pattern):
        return m.group(1)
    if m := _STRING_LITERAL.match(pattern):
        return m.group(1)
    return None


def vocabulary_report(text: str, vocab: dict) -> dict:
    """Phase 2b evidence-vocabulary classification of one policy's temporal predicates (TEXT, never a score).

    vocab: authority_action, vendor_actions, contract_values, vendor_stated_values, approver_kind_fields (requirements.yaml
    `evidence_vocabulary`). Per predicate: role (authority / vendor / other) and each literal's classes (contract and/or
    vendor_stated, else neither). Policy-level: actions bound; `binding` (authority | vendor | both | authority+other |
    vendor+other | other | none); the literals of authority-bound predicates by class; `vendor_token_in_authority_predicate`
    (an authority literal that is vendor-stated and NOT a contract value: borrowed vocabulary); `invented_in_authority_predicate`
    (an authority literal in neither set); `approver_kind_present` (any predicate binds one of approver_kind_fields)."""
    contract, stated = set(vocab["contract_values"]), set(vocab["vendor_stated_values"])
    vendor_actions, approver_fields = set(vocab["vendor_actions"]), set(vocab["approver_kind_fields"])
    preds = []
    for p in predicate_tally(text)["predicates"]:
        role = "authority" if p["action"] == vocab["authority_action"] else "vendor" if p["action"] in vendor_actions else "other"
        lits = {}
        for f, v in p["fields"].items():
            if (lid := literal_id(v)) is not None:
                classes = [c for c, s in (("contract", contract), ("vendor_stated", stated)) if lid in s] or ["neither"]
                lits[f] = {"value": lid, "classes": classes}
        preds.append({"action": p["action"], "kind": p["kind"], "role": role, "literals": lits,
                      "approver_kind_bound": sorted(set(p["fields"]) & approver_fields)})
    roles = {p["role"] for p in preds}
    if not preds:
        binding = "none"
    elif {"authority", "vendor"} <= roles:
        binding = "both"
    elif roles == {"authority"}:
        binding = "authority"
    elif roles == {"vendor"}:
        binding = "vendor"
    elif "authority" in roles:
        binding = "authority+other"
    elif "vendor" in roles:
        binding = "vendor+other"
    else:
        binding = "other"
    auth = {"contract": set(), "vendor_stated": set(), "neither": set()}
    for p in preds:
        if p["role"] == "authority":
            for lit in p["literals"].values():
                for c in lit["classes"]:
                    auth[c].add(lit["value"])
    auth_sorted = {k: sorted(v) for k, v in auth.items()}
    return {"predicates": preds, "actions_bound": sorted({p["action"] for p in preds}), "binding": binding,
            "authority_literals": auth_sorted,
            "vendor_token_in_authority_predicate": bool(auth["vendor_stated"] - contract),
            "invented_in_authority_predicate": bool(auth["neither"]),
            "approver_kind_present": any(p["approver_kind_bound"] for p in preds)}


def tally_run(run: Path) -> dict:
    """Per generator: counts of predicate (action, kind), of output-field literals, of permitted/forbidden actions."""
    run = Path(run)
    out = {}
    for policy in sorted(run.glob("*/*/sample_*/policy.dw")):
        gen = policy.parents[1].name
        t = predicate_tally(policy.read_text())
        g = out.setdefault(gen, {"samples": 0, "predicate_action_kind": Counter(), "predicate_fields": Counter(),
                                 "literal_by_field": Counter(), "permit_actions": Counter(), "forbid_actions": Counter(),
                                 "predicates_per_sample": Counter()})
        g["samples"] += 1
        g["predicates_per_sample"][len(t["predicates"])] += 1
        for p in t["predicates"]:
            g["predicate_action_kind"][f'{p["action"]}::{p["kind"]}'] += 1
            for f, v in p["fields"].items():
                g["predicate_fields"][f] += 1
                if v.startswith('"'):
                    g["literal_by_field"][f"{f} = {v}"] += 1
        g["permit_actions"].update(t["permit_actions"])
        g["forbid_actions"].update(t["forbid_actions"])
    return {gen: {k: (dict(sorted(v.items(), key=lambda kv: (-kv[1], str(kv[0])))) if isinstance(v, Counter) else v)
                  for k, v in g.items()} for gen, g in out.items()}


if __name__ == "__main__":
    print(json.dumps(tally_run(Path(sys.argv[1])), indent=1))
