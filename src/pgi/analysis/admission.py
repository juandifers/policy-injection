"""Deterministic admission checker for temporal evidence policies (Phase 2c A5). No LLM; text only; fail closed.

The catalogue is a TRUSTED file beside a scenario's written contract (e.g. `admission.catalogue.yaml`), derived from the
contract text, never from a gold policy:

    protected_action: close_workorder
    evidence: {action: authority_get_approval, kind: response, max_window: 1h}
    correlations: [site_id, wonum]                       # input.<f>: context.input.<f>
    authorizing_values: {decision: GRANTED, approver_kind: HUMAN}   # output.<f> equals it: plain string or enum-entity id

Rule. Take every `permit` that can apply to the protected action (scope `action == it`, an action list containing it, a
schema-declared action group containing it, or an unconstrained `action`). REJECT the policy if any such permit
  - has no `when temporal` clause;
  - has, in every temporal block, some alternative branch (`||`, not valid Dogwood but checked textually) without a
    conforming catalogued predicate: a permit is admitted when at least one of its (conjoined) temporal blocks carries a
    conforming predicate in every branch;
  - uses a construct the checker does not model: anything inside a temporal block other than `formerly within W P`,
    `previous within W P`, `!A since within W B` (B is the evidence side) or a negated predicate; or a scope the schema
    cannot resolve.
A conforming predicate names the catalogued action and kind, carries both correlations, constrains every authorizing
output field to its value, and has a window within the limit. Extra conjuncts (Cedar `when`/`unless`, negated predicates,
further evidence predicates, extra fields) are admitted and reported. Forbids are ignored. Every rejection carries a reason.
A policy with no applicable permit is admitted and flagged `vacuous`.

This is a text check of the policy's shape against the contract, not the oracle (which replays traces) and not a proof.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import yaml

from pgi.analysis.dogwood_text import _PREDICATE, _BINDING, _balanced_end, _split_top, action_groups, applies_to, literal_id, statements

CATALOGUE_KEYS = {"protected_action", "evidence", "correlations", "authorizing_values"}
EVIDENCE_KEYS = {"action", "kind", "max_window"}
_WINDOW = r"(\d+[smhd])"
_FORMERLY = re.compile(rf"^(formerly|previous)\s+within\s+{_WINDOW}\s+(.*)$", re.DOTALL)
_SINCE = re.compile(rf"^!\s*(.*?)\s+since\s+within\s+{_WINDOW}\s+(.*)$", re.DOTALL)
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def load_catalogue(path: Path) -> dict:
    """Load and validate a catalogue file."""
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict) or set(data) != CATALOGUE_KEYS:
        raise ValueError(f"{path}: catalogue must have exactly the keys {sorted(CATALOGUE_KEYS)}, got {sorted(data) if isinstance(data, dict) else type(data)}")
    if not isinstance(data["evidence"], dict) or set(data["evidence"]) != EVIDENCE_KEYS:
        raise ValueError(f"{path}: evidence must have exactly the keys {sorted(EVIDENCE_KEYS)}")
    if window_seconds(str(data["evidence"]["max_window"])) is None:
        raise ValueError(f"{path}: max_window {data['evidence']['max_window']!r} is not <n><s|m|h|d>")
    if not isinstance(data["correlations"], list) or not data["correlations"]:
        raise ValueError(f"{path}: correlations must be a non-empty list of input field names")
    if not isinstance(data["authorizing_values"], dict) or not data["authorizing_values"]:
        raise ValueError(f"{path}: authorizing_values must be a non-empty mapping output field -> value")
    return {"protected_action": str(data["protected_action"]),
            "evidence": {k: str(v) for k, v in data["evidence"].items()},
            "correlations": [str(c) for c in data["correlations"]],
            "authorizing_values": {str(k): str(v) for k, v in data["authorizing_values"].items()}}


def window_seconds(w: str) -> int | None:
    if m := re.fullmatch(r"(\d+)([smhd])", w.strip()):
        return int(m.group(1)) * _UNITS[m.group(2)]
    return None


def _strip_parens(s: str) -> str:
    s = s.strip()
    while s.startswith("(") and _balanced_end(s, 0) == len(s):
        s = s[1:-1].strip()
    return s


def _one_predicate(s: str) -> dict | None:
    s = _strip_parens(s)
    if m := _PREDICATE.fullmatch(s):
        _, action, kind, body = m.groups()
        return {"action": action, "kind": kind, "fields": {f: v for f, v in _BINDING.findall(body)}}
    return None


def _conjunct(text: str) -> dict:
    """Classify one top-level conjunct of a temporal block: evidence (formerly / previous / since), negated, or unmodeled."""
    s = _strip_parens(text)
    if m := _FORMERLY.match(s):
        if pred := _one_predicate(m.group(3)):
            return {"kind": "evidence", "op": m.group(1), "window": m.group(2), "pred": pred, "text": s}
    if m := _SINCE.match(s):
        a, b = _one_predicate(m.group(1)), _one_predicate(m.group(3))
        if a and b:
            return {"kind": "evidence", "op": "since", "window": m.group(2), "pred": b, "guard": a, "text": s}
    if s.startswith("!"):
        inner = _strip_parens(s[1:])
        fm = _FORMERLY.match(inner)
        if (fm and _one_predicate(fm.group(3))) or _one_predicate(inner):
            return {"kind": "negated", "text": s}
    return {"kind": "unmodeled", "text": s}


def _conforms(ev: dict, cat: dict) -> tuple[list[str], list[str]]:
    """(reasons it does not conform; extra fields it carries). Empty reasons = conforming."""
    p, e, reasons = ev["pred"], cat["evidence"], []
    if p["action"] != e["action"]:
        reasons.append(f"action {p['action']} is not {e['action']}")
    if p["kind"] != e["kind"]:
        reasons.append(f"kind {p['kind']} is not {e['kind']}")
    expected = set()
    for f in cat["correlations"]:
        key, want = f"input.{f}", f"context.input.{f}"
        expected.add(key)
        got = p["fields"].get(key)
        if got is None:
            reasons.append(f"missing correlation {key}: {want}")
        elif got != want:
            reasons.append(f"{key} is {got}, not {want}")
    for f, v in cat["authorizing_values"].items():
        key = f"output.{f}"
        expected.add(key)
        got = p["fields"].get(key)
        if got is None:
            reasons.append(f"{key} is not constrained")
        elif literal_id(got) != v:
            reasons.append(f"{key} is {got}, not {v}")
    secs, limit = window_seconds(ev["window"]), window_seconds(e["max_window"])
    if secs is None or secs > limit:
        reasons.append(f"window {ev['window']} exceeds {e['max_window']}")
    return reasons, sorted(set(p["fields"]) - expected)


def _check_permit(index: int, s: dict, cat: dict) -> dict:
    rec = {"index": index, "id": s["id"], "scope": s["scope"], "verdict": "admitted", "reasons": [],
           "evidence": [], "extra_conjuncts": [f"cedar: {c['kind']}" for c in s["cedar_conditions"]]}
    if not s["temporal_blocks"]:
        rec["reasons"], rec["verdict"] = ["no temporal evidence clause"], "rejected"
        return rec
    unmodeled, any_block_ok, failing = [], False, []
    for bi, body in enumerate(s["temporal_blocks"]):
        branches = _split_top(body, "||")
        branch_ok = []
        for br_i, br in enumerate(branches):
            ok = False
            for text in _split_top(br, "&&"):
                if not text.strip():
                    continue
                c = _conjunct(text)
                if c["kind"] == "unmodeled":
                    unmodeled.append(f"unmodeled construct: {' '.join(c['text'].split())[:100]}")
                elif c["kind"] == "negated":
                    rec["extra_conjuncts"].append(f"negated: {' '.join(c['text'].split())[:100]}")
                else:
                    why, extra = _conforms(c, cat)
                    rec["evidence"].append({"op": c["op"], "window": c["window"], "action": c["pred"]["action"], "kind": c["pred"]["kind"],
                                            "conforming": not why, "reasons": why, "extra_fields": extra, "block": bi, "branch": br_i})
                    if why:
                        rec["extra_conjuncts"].append(f"evidence predicate {c['pred']['action']}::{c['pred']['kind']} within {c['window']} not catalogued: " + "; ".join(why))
                    else:
                        ok = True
            branch_ok.append(ok)
        if all(branch_ok):
            any_block_ok = True
        elif len(branches) > 1:
            failing += [f"temporal block {bi + 1}: branch {i + 1} of {len(branches)} lacks a conforming predicate" for i, ok in enumerate(branch_ok) if not ok]
    if unmodeled:
        rec["reasons"] += unmodeled
    if not any_block_ok:
        candidates = [f"{e['action']}::{e['kind']} within {e['window']}: " + "; ".join(e["reasons"]) for e in rec["evidence"] if not e["conforming"]]
        rec["reasons"].append("no conforming catalogued evidence predicate in every branch" + (": " + " | ".join(candidates) if candidates else " (no evidence predicate)"))
        rec["reasons"] += failing
    if rec["reasons"]:
        rec["verdict"] = "rejected"
    return rec


def check_policy(text: str, cat: dict, schema_text: str | None = None) -> dict:
    """Admission verdict for one policy text under a catalogue (see module doc). `schema_text` resolves action groups."""
    groups = action_groups(schema_text) if schema_text is not None else None
    permits, out = [s for s in statements(text) if s["effect"] == "permit"], []
    for i, s in enumerate(permits):
        applies, resolved = applies_to(s["scope"], cat["protected_action"], groups)
        if not resolved:
            out.append({"index": i, "id": s["id"], "scope": s["scope"], "verdict": "rejected", "evidence": [], "extra_conjuncts": [],
                        "reasons": [f"cannot resolve action scope {s['scope']} (unknown action group or scope form): fail closed"]})
        elif applies:
            out.append(_check_permit(i, s, cat))
    reasons = [f"permit {p['id'] or '#' + str(p['index'])}: {r}" for p in out if p["verdict"] == "rejected" for r in p["reasons"]]
    return {"admitted": not reasons, "vacuous": not reasons and not out, "reasons": reasons, "permits": out,
            "protected_action": cat["protected_action"]}


def check_run(run: Path, cat: dict) -> dict:
    """Check every final policy (`<scenario>/<generator>/sample_*/policy.dw`) of one temporal-clean run folder, next to
    its recorded behaviour (oracle.json): valid, scored, exact = gold allow-set, allows a vendor-only trace."""
    run = Path(run)
    config = json.loads((run / "config.json").read_text())
    schema_text = (run / config["frame"]["schema"]).read_text()
    gold = set(config["frame"]["gold_allow_set"])
    out = {"run_id": config["run_id"], "arm": config.get("arm", {}).get("name", "base"), "scenario": config["scenario"],
           "input_mode": config.get("input_mode", "manifests"), "generators": {}}
    for gen_dir in sorted(p for p in (run / config["scenario"]).iterdir() if p.is_dir()):
        rows = []
        for d in sorted(gen_dir.glob("sample_*")):
            text = (d / "policy.dw").read_text()
            o = json.loads((d / "oracle.json").read_text())
            r = check_policy(text, cat, schema_text)
            scored = bool(o.get("scored"))
            rows.append({"sample": int(d.name.split("_")[1]), "policy_sha256": hashlib.sha256(text.encode()).hexdigest(),
                         "admitted": r["admitted"], "vacuous": r["vacuous"], "reasons": r["reasons"],
                         "valid": bool(o.get("valid")), "scored": scored,
                         "exact": scored and set(o["allow_set"]) == gold,
                         "allows_vendor_only": bool(o.get("allows_vendor_only")) if scored else False})
        out["generators"][gen_dir.name] = rows
    return out


def reason_class(reason: str) -> str:
    """Coarse class of a rejection reason, for counting."""
    body = reason.split(": ", 1)[1] if reason.startswith("permit ") and ": " in reason else reason
    for key in ("no temporal evidence clause", "unmodeled construct", "cannot resolve action scope", "no conforming catalogued evidence predicate"):
        if body.startswith(key):
            return key
    return "other"


def summarize_check(report: dict) -> dict:
    """Per generator: admitted / rejected / vacuous counts, reason classes, and the four Part C cross-tabs."""
    out = {}
    for gen, rows in report["generators"].items():
        rejected = [r for r in rows if not r["admitted"]]
        out[gen] = {
            "n": len(rows), "admitted": sum(r["admitted"] for r in rows), "rejected": len(rejected),
            "vacuous": sum(r["vacuous"] for r in rows),
            "reason_classes": dict(sorted(Counter(c for r in rejected for c in sorted({reason_class(x) for x in r["reasons"]})).items())),
            "rejected_allowing_vendor_only": sorted(r["sample"] for r in rejected if r["allows_vendor_only"]),
            "admitted_allowing_vendor_only": sorted(r["sample"] for r in rows if r["admitted"] and r["allows_vendor_only"]),
            "admitted_not_exact": sorted(r["sample"] for r in rows if r["admitted"] and not r["exact"]),
            "exact_rejected": sorted(r["sample"] for r in rejected if r["exact"]),
            "admitted_invalid": sorted(r["sample"] for r in rows if r["admitted"] and not r["valid"]),
        }
    return out
