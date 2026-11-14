"""Default-reliance detector, by behaviour. No LLM.

A manifest's `default` is vendor text: the schema generator drops it and a policy cannot see it. A policy
relies on it when it treats an omitted field as if it held the default. Behaviourally, for every universe
request R the policy allows that sets a top-level tool argument whose manifest property declares a default:

  R_omit  = R with that field removed from context.<input_key>
  R_alt_v = R with the field set to an alternative value v, for each candidate v

  omission_denied  R_omit denied                         (the policy requires the field: no reliance)
  relies           R_omit allowed and some R_alt_v denied (the policy constrains the field, yet lets
                                                           absence through: it assumes the default)
  unconstrained    R_omit allowed and every R_alt_v allowed (the policy ignores the field)
  untestable       R_omit allowed and no candidate exists

Candidates (the set value itself excluded): the other boolean for a boolean, the manifest property's
`enum` members, and the values the field takes in other universe cases for the same tool. Values are in
the universe's own encoding; the default is not re-encoded, so it is never a candidate by itself.

Conventions (from the MCP schema generator, not from any domain): the action id is the tool name, and the
tool arguments are the record context.<input_key>. Nested properties are not examined. A derived request
that errors raises (errors are not denies).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from pgi.oracle.enumeration import Universe, allowed
from pgi.oracle.errors import OracleError


def _defaulted(manifests: dict[str, Path]) -> dict[str, dict[str, dict]]:
    """{tool: {field: manifest property}} for top-level properties that declare a default."""
    out: dict[str, dict[str, dict]] = {}
    seen: dict[str, str] = {}
    for server, path in manifests.items():
        for tool in json.loads(Path(path).read_text()).get("tools", []):
            name = tool["name"]
            if name in seen:
                raise OracleError(f"tool {name!r} declared by both {seen[name]!r} and {server!r}")
            seen[name] = server
            props = (tool.get("inputSchema") or {}).get("properties") or {}
            out[name] = {f: p for f, p in props.items() if "default" in p}
    return out


def _with_input(req: dict, input_key: str, field: str, value=..., omit: bool = False) -> dict:
    req = json.loads(json.dumps(req))
    inp = req["context"][input_key]
    if omit:
        del inp[field]
    else:
        inp[field] = value
    return req


def default_reliance(policy: Path, universe: Universe, schema: Path, manifests: dict[str, Path],
                     input_key: str = "input") -> list[dict]:
    """One row per (allowed case, defaulted field it sets): {case, tool, field, default, set_value,
    omitted_allowed, alternatives: [{value, allowed}], verdict}."""
    defaulted = _defaulted(manifests)
    allow = allowed(policy, universe, schema)
    observed: dict[tuple[str, str], list] = {}
    for req in universe.requests.values():
        for f, v in ((req.get("context") or {}).get(input_key) or {}).items():
            vals = observed.setdefault((req["action"]["id"], f), [])
            if v not in vals:
                vals.append(v)

    probes: dict[str, dict] = {}
    rows = []
    for cid in sorted(allow):
        req = universe.requests[cid]
        tool = req["action"]["id"]
        inp = (req.get("context") or {}).get(input_key) or {}
        for field, prop in defaulted.get(tool, {}).items():
            if field not in inp:
                continue
            value = inp[field]
            cands = []
            for v in ([not value] if isinstance(value, bool) else []) + list(prop.get("enum") or []) \
                    + observed.get((tool, field), []):
                if v != value and v not in cands:
                    cands.append(v)
            key = f"{cid}::{field}"
            probes[f"{key}::omit"] = _with_input(req, input_key, field, omit=True)
            for i, v in enumerate(cands):
                probes[f"{key}::alt{i}"] = _with_input(req, input_key, field, v)
            rows.append({"case": cid, "tool": tool, "field": field, "default": prop["default"],
                         "set_value": value, "_key": key, "_cands": cands})
    if not rows:
        return []
    got = allowed(policy, Universe(probes, universe.entities, universe.defaults), schema)
    for r in rows:
        key, cands = r.pop("_key"), r.pop("_cands")
        r["omitted_allowed"] = f"{key}::omit" in got
        r["alternatives"] = [{"value": v, "allowed": f"{key}::alt{i}" in got} for i, v in enumerate(cands)]
        if not r["omitted_allowed"]:
            r["verdict"] = "omission_denied"
        elif not cands:
            r["verdict"] = "untestable"
        elif all(a["allowed"] for a in r["alternatives"]):
            r["verdict"] = "unconstrained"
        else:
            r["verdict"] = "relies"
    return rows


def summarize_reliance(rows: list[dict]) -> dict:
    """{relies: n, by_field: {"tool.field": n relying rows}, verdicts: {verdict: n}}."""
    relying = [r for r in rows if r["verdict"] == "relies"]
    return {"relies": len(relying),
            "by_field": dict(sorted(Counter(f'{r["tool"]}.{r["field"]}' for r in relying).items())),
            "verdicts": dict(sorted(Counter(r["verdict"] for r in rows).items()))}
