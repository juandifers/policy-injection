"""Cause tags: which condition of a policy denies one request. Deterministic; no LLM.

For a surplus case, explain with the reference (which conjunct of P_ref denies it). For a deficit case,
explain with the candidate (which conjunct of P denies it).

Method, per denied request:
  1. Translate the policy to Cedar's JSON form (`cedar translate-policy`). Each policy whose action scope
     covers the request's action is a probe target; coverage is decided by evaluating a scope-only permit
     (so `action in [...]` lists and action groups are handled by Cedar, not by us).
  2. Forbids first: each matching forbid is evaluated on its own, as a permit with the same scope and
     conditions. If one is satisfied, the tag is "forbid: <id>".
  3. No matching permit: "action not granted".
  4. Each matching permit is split into conjuncts:
       conjunct 0 = its principal/resource scope ("scope"; only listed when not `All`),
       then every `when` body with top-level `&&` flattened recursively on both sides,
       then each `unless` body as one negated conjunct `!(...)`.
     A `||` inside a conjunct is not split: that whole conjunct is the tag.
  5. Variants, all as permits with the request's action scope: every prefix (conjuncts 1..j, with the
     scope), the full permit, and every leave-one-out (all but conjunct i). They are evaluated in ONE
     cedarpy call; `diagnostics.reasons` names the satisfied variants and `diagnostics.errors` the
     variants whose evaluation raised (Cedar skips an erroring policy; we never treat that as a deny).
  6. first_blocker: the first conjunct whose prefix is not satisfied (prefixes keep `has` guards
     short-circuiting). If that prefix raised, the tag is "unexplained: error".
     sole_blockers: condition units whose removal alone flips the request to allowed (see `_units`: a
     non-guard conjunct plus the has-guards only it needs). A removal that raises counts as no flip and is
     listed in loo_errors. Unlike the prefix scan, this does not depend on the order the conditions were written.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import tempfile
from pathlib import Path

import cedarpy

from pgi.oracle.enumeration import Universe
from pgi.oracle.errors import OracleError

_ALL = {"op": "All"}
_ERR = re.compile(r"^error while evaluating policy `(policy\d+)`")


def _cedar(*args: str, stdin: str | None = None) -> str:
    proc = subprocess.run(["cedar", *args], capture_output=True, text=True, input=stdin)
    if proc.returncode != 0:
        raise OracleError(f"cedar {' '.join(args)} failed: {(proc.stdout + proc.stderr).strip()}")
    return proc.stdout


def _to_json(policy: Path) -> dict:
    return json.loads(_cedar("translate-policy", "--direction", "cedar-to-json", "--policies", str(policy)))


def _to_cedar(static: dict[str, dict]) -> str:
    """Cedar text of a JSON static policy set, in the given order (cedarpy names them policy0, policy1, ...).

    The CLI emits policies ordered by JSON key, not insertion order, so keys are zero-padded positions.
    `_evaluate` checks the resulting numbering against the @id annotations and fails loudly on a mismatch.
    """
    keyed = {f"{n:06d}": pol for n, pol in enumerate(static.values())}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"staticPolicies": keyed, "templates": {}, "templateLinks": []}, f)
    text = _cedar("translate-policy", "--direction", "json-to-cedar", "--policies", f.name)
    Path(f.name).unlink()
    return text


def _flatten(expr: dict) -> list[dict]:
    if "&&" in expr:
        return _flatten(expr["&&"]["left"]) + _flatten(expr["&&"]["right"])
    return [expr]


def _and(exprs: list[dict]) -> dict | None:
    out = None
    for e in exprs:
        out = e if out is None else {"&&": {"left": out, "right": e}}
    return out


def _conjuncts(pol: dict) -> list[dict]:
    """[(kind, expr)] where kind is 'scope' or 'cond'."""
    out = []
    if pol["principal"] != _ALL or pol["resource"] != _ALL:
        out.append(("scope", {"principal": pol["principal"], "resource": pol["resource"]}))
    for c in pol.get("conditions", []):
        if c["kind"] == "when":
            out += [("cond", e) for e in _flatten(c["body"])]
    for c in pol.get("conditions", []):
        if c["kind"] == "unless":
            out.append(("cond", {"!": {"arg": c["body"]}}))
    return out


def _key(e: dict) -> str:
    return json.dumps(e, sort_keys=True)


def _accesses(node) -> set[tuple[str, str]]:
    """Every attribute access (left expression, attr) in an expression: `{".": {left, attr}}` nodes."""
    out = set()
    if isinstance(node, dict):
        if "." in node and isinstance(node["."], dict):
            out.add((_key(node["."]["left"]), node["."]["attr"]))
        for v in node.values():
            out |= _accesses(v)
    elif isinstance(node, list):
        for v in node:
            out |= _accesses(v)
    return out


def _units(parts: list[tuple[str, dict]]) -> list[list[int]]:
    """Condition units: each non-guard conjunct with the has-guards only it needs (transitively).

    A guard is a conjunct `L has a`; conjunct i needs it if i accesses `L.a` anywhere (matched on the JSON
    form: same left expression, same attribute). A guard needed by several non-guard conjuncts is in no unit
    (it stays when any one is removed). A guard nothing needs is a unit by itself. The scope is its own unit.
    """
    guard = {i: (_key(e["has"]["left"]), e["has"]["attr"]) for i, (k, e) in enumerate(parts)
             if k == "cond" and "has" in e}
    needs = {i: {g for g, gk in guard.items() if g != i and gk in _accesses(e)}
             for i, (k, e) in enumerate(parts) if k == "cond"}
    heads = [i for i in range(len(parts)) if i not in guard]
    req = {}
    for i in heads:
        seen, todo = set(), list(needs.get(i, ()))
        while todo:
            g = todo.pop()
            if g not in seen:
                seen.add(g)
                todo += needs.get(g, ())
        req[i] = seen
    dependents = {g: {i for i in heads if g in req[i]} for g in guard}
    units = []
    for i in range(len(parts)):
        if i in guard:
            if not dependents[i]:
                units.append([i])
        else:
            units.append(sorted({i} | {g for g in req[i] if dependents[g] == {i}}))
    return units


def _variant(action_scope: dict, parts: list[tuple[str, dict]], vid: str) -> dict:
    """A permit holding exactly these conjuncts (scope parts restore principal/resource)."""
    pol = {"effect": "permit", "principal": _ALL, "action": action_scope, "resource": _ALL,
           "conditions": [], "annotations": {"id": vid}}
    conds = []
    for kind, e in parts:
        if kind == "scope":
            pol["principal"], pol["resource"] = e["principal"], e["resource"]
        else:
            conds.append(e)
    if conds:
        pol["conditions"] = [{"kind": "when", "body": _and(conds)}]
    return pol


def _texts(parts: list[tuple[str, dict]]) -> list[str]:
    """Readable Cedar text of each conjunct, via the CLI's JSON -> Cedar translation."""
    static = {}
    for i, (kind, e) in enumerate(parts):
        static[f"t{i}"] = _variant(_ALL, [(kind, e)], f"t{i}")
    text = _to_cedar(static)
    out = []
    for i, (kind, _) in enumerate(parts):
        block = text.split(f'@id("t{i}")', 1)[1].split("};", 1)[0]
        if kind == "scope":
            head = block.split(")", 1)[0].split("(", 1)[1]
            out.append("scope: " + ", ".join(l.strip().rstrip(",") for l in head.splitlines()
                                             if l.strip() and not l.strip().startswith("action")))
        else:
            body = block.split("when {", 1)[1].rsplit("}", 1)[0]
            out.append(" ".join(body.split()))
    return out


def _evaluate(static: dict[str, dict], request: dict, entities: list, schema: Path) -> tuple[set[str], set[str]]:
    """(satisfied variant ids, erroring variant ids) for one request, in one cedarpy call."""
    ids = [p["annotations"]["id"] for p in static.values()]
    res = cedarpy.is_authorized(request, _to_cedar(static), entities, Path(schema).read_text())
    by_reason = res.diagnostics.id_annotations_by_reason or {}
    for internal, ann in by_reason.items():  # cedarpy numbers policies by position; check that it did
        if ids[int(internal.removeprefix("policy"))] != ann:
            raise OracleError(f"cedarpy policy numbering does not match the variant order ({internal} = {ann})")
    satisfied = {by_reason[r] for r in res.diagnostics.reasons}
    errored = set()
    for msg in res.diagnostics.errors:
        m = _ERR.match(msg)
        if not m:
            raise OracleError(f"unrecognised cedarpy diagnostic: {msg}")
        errored.add(ids[int(m.group(1).removeprefix("policy"))])
    return satisfied, errored


def _matching(pols: list[tuple[str, dict]], request: dict, entities: list, schema: Path) -> list[tuple[str, dict]]:
    """The policies whose action scope covers the request's action, decided by evaluation (handles groups)."""
    probes = {f"a{k}": {"effect": "permit", "principal": _ALL, "action": p["action"], "resource": _ALL,
                        "conditions": [], "annotations": {"id": f"a{k}"}} for k, (_, p) in enumerate(pols)}
    if not probes:
        return []
    sat, err = _evaluate(probes, request, entities, schema)
    if err:
        raise OracleError(f"action-scope probe raised: {sorted(err)}")
    return [pp for k, pp in enumerate(pols) if f"a{k}" in sat]


def explain(policy: Path, case_id: str, universe: Universe, schema: Path) -> dict:
    """Why does `policy` deny request `case_id`? See the module docstring."""
    request = universe.requests[case_id]
    action = request["action"]
    doc = _to_json(policy)
    if doc.get("templates") or doc.get("templateLinks"):
        raise OracleError(f"{policy}: templates are not supported by cause tags")
    pols = _matching([(p.get("annotations", {}).get("id", pid), p) for pid, p in doc["staticPolicies"].items()],
                     request, universe.entities, schema)
    act_scope = {"op": "==", "entity": action}
    static, plan = {}, []
    for k, (pid, p) in enumerate(pols):
        parts = _conjuncts(p)
        if p["effect"] == "forbid":
            static[f"f{k}"] = _variant(act_scope, parts, f"f{k}")
            plan.append(("forbid", pid, parts, None))
            continue
        for j in range(len(parts) + 1):
            static[f"p{k}:{j}"] = _variant(act_scope, parts[:j], f"p{k}:{j}")
        units = _units(parts)
        for u, members in enumerate(units):
            static[f"l{k}:{u}"] = _variant(act_scope, [x for i, x in enumerate(parts) if i not in members], f"l{k}:{u}")
        plan.append(("permit", pid, parts, units))
    sat, err = _evaluate(static, request, universe.entities, schema) if static else (set(), set())

    out = {"case": case_id, "action": f'{action["type"]}::{json.dumps(action["id"])}', "forbids": [], "permits": []}
    for k, (effect, pid, parts, units) in enumerate(plan):
        if effect == "forbid":
            fired = f"f{k}" in sat
            out["forbids"].append({"id": pid, "fired": fired,
                                   "error": "evaluation error (Cedar skips this forbid)" if f"f{k}" in err else None})
            continue
        texts = _texts(parts) if parts else []
        n = len(parts)
        is_guard = lambda i: parts[i][0] == "cond" and "has" in parts[i][1]
        unit_rows = []
        for m in units:  # a unit is one head plus its private guards, or one lone guard
            head = next((i for i in m if not is_guard(i)), m[0])
            unit_rows.append({"head": texts[head], "guards": [texts[i] for i in m if i != head]})
        row = {"id": pid, "conjuncts": texts, "units": unit_rows, "allows": f"p{k}:{n}" in sat, "first_blocker": None,
               "first_blocker_index": None, "first_blocker_error": False, "sole_blockers": [], "sole_blocker_units": [],
               "loo_errors": []}
        if not row["allows"]:
            j = next(j for j in range(n + 1) if f"p{k}:{j}" not in sat)
            row["first_blocker_index"] = j
            row["first_blocker"] = texts[j - 1] if j > 0 else None
            row["first_blocker_error"] = f"p{k}:{j}" in err
            for u, ur in enumerate(unit_rows):
                if f"l{k}:{u}" in sat:
                    row["sole_blockers"].append(ur["head"])
                    row["sole_blocker_units"].append(ur)
                elif f"l{k}:{u}" in err:
                    row["loo_errors"].append(ur["head"])
        out["permits"].append(row)

    fired = [f["id"] for f in out["forbids"] if f["fired"]]
    if fired:
        out["tag"] = f"forbid: {fired[0]}"
    elif not out["permits"]:
        out["tag"] = "action not granted"
    else:
        tags = []
        for p in out["permits"]:
            if p["allows"]:
                tags.append(f"{p['id']}: allows")
            elif p["first_blocker_error"] or p["first_blocker"] is None:
                tags.append(f"{p['id']}: unexplained: error" if p["first_blocker_error"]
                            else f"{p['id']}: unexplained: empty permit denies")
            else:
                tags.append(f"{p['id']}: {p['first_blocker']}")
        out["tag"] = tags
    return out


def causes(policy: Path, reference: Path, surplus: list[str], deficit: list[str],
           universe: Universe, schema: Path) -> dict:
    """Cause tags for every surplus case (explained by the reference) and deficit case (by the candidate)."""
    return {"surplus": {c: explain(reference, c, universe, schema) for c in surplus},
            "deficit": {c: explain(policy, c, universe, schema) for c in deficit}}
