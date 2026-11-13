"""Literal provenance: for each literal a policy compares against, which inputs contain it. No LLM.

Literals come from Cedar's JSON policy form (`cedar translate-policy --direction cedar-to-json`), never
from regexes over Cedar text:
  - strings and longs: every `{"Value": ...}` (booleans are not literals);
  - entity ids: `{"Value": {"__entity": ...}}` in conditions, and `entity` / `entities` in scopes;
  - `like` patterns: kind "like"; each wildcard-separated segment must occur for a source to count.
Entity *types* (`is`), attribute names and record keys are accessors, not literals.

A literal occurs in an input if its token (a string's value, an entity's id, a long's decimal text) appears
as a whole token, case-sensitively: not preceded or followed by [A-Za-z0-9_]. Source classes:
  intent, trusted_schema, generated_schema,
  manifest_structure  (tool names, property names, enum values),
  manifest_free_text  (description, title, at any depth),
  manifest_other      (every other string or number leaf, e.g. type, default, required).
A literal may have several sources or none; all are recorded with locations.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

CLASSES = ("intent", "trusted_schema", "generated_schema",
           "manifest_structure", "manifest_free_text", "manifest_other")
_FREE_TEXT_KEYS = ("description", "title")


@dataclass(frozen=True)
class Literal:
    """One literal as written in the policy. `text` is its Cedar spelling; `tokens` are what must occur."""

    kind: str          # string | long | entity | like
    text: str
    tokens: tuple[str, ...]


def _policy_json(policy: Path) -> dict:
    proc = subprocess.run(["cedar", "translate-policy", "--direction", "cedar-to-json", "--policies", str(policy)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise ValueError(f"{policy} does not parse: {(proc.stdout + proc.stderr).strip()}")
    return json.loads(proc.stdout)


def _entity(e: dict) -> Literal:
    return Literal("entity", f'{e["type"]}::{json.dumps(e["id"])}', (e["id"],))


def _walk(node, out: list[Literal]) -> None:
    if isinstance(node, list):
        for x in node:
            _walk(x, out)
    elif isinstance(node, dict):
        for key, val in node.items():
            if key == "Value":
                if isinstance(val, dict) and "__entity" in val:
                    out.append(_entity(val["__entity"]))
                elif isinstance(val, bool):
                    pass
                elif isinstance(val, int):
                    out.append(Literal("long", str(val), (str(val),)))
                elif isinstance(val, str):
                    out.append(Literal("string", json.dumps(val), (val,)))
                else:
                    _walk(val, out)
            elif key == "like" and isinstance(val, dict):
                _walk(val.get("left"), out)
                segs, cur = [], ""
                for part in val["pattern"]:
                    if part == "Wildcard":
                        segs.append(cur)
                        cur = ""
                    else:
                        cur += part["Literal"]
                segs.append(cur)
                text = "*".join(s.replace("*", "\\*") for s in segs)
                out.append(Literal("like", json.dumps(text), tuple(s for s in segs if s)))
            else:
                _walk(val, out)


def extract_literals(policy: Path) -> list[Literal]:
    """Every literal occurrence in scopes and conditions, in policy order (duplicates kept)."""
    doc = _policy_json(policy)
    out: list[Literal] = []
    for pol in [*doc.get("staticPolicies", {}).values(), *doc.get("templates", {}).values()]:
        for slot in ("principal", "action", "resource"):
            scope = pol.get(slot, {})
            for e in [scope.get("entity"), *(scope.get("entities") or []), (scope.get("in") or {}).get("entity")]:
                if e:
                    out.append(_entity(e))
        for cond in pol.get("conditions", []):
            _walk(cond["body"], out)
    return out


def _manifest_leaves(server: str, manifest: dict) -> list[tuple[str, str, str]]:
    """(class, location, text) for every leaf of a tools/list manifest."""
    out = []

    def walk(node, path: str, parent_key: str | None) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                p = f"{path}.{k}"
                if parent_key == "properties":
                    out.append(("manifest_structure", p, k))      # property name
                if k == "enum" and isinstance(v, list):
                    for i, x in enumerate(v):
                        if not isinstance(x, (dict, list)):
                            out.append(("manifest_structure", f"{p}[{i}]", json.dumps(x) if isinstance(x, bool) else str(x)))
                    continue
                if k in _FREE_TEXT_KEYS and isinstance(v, str):
                    out.append(("manifest_free_text", p, v))
                    continue
                walk(v, p, k)
        elif isinstance(node, list):
            for i, x in enumerate(node):
                walk(x, f"{path}[{i}]", None)
        elif node is not None and not isinstance(node, bool):
            out.append(("manifest_other", path, str(node)))

    for tool in manifest.get("tools", []):
        name = tool.get("name", "?")
        for k, v in tool.items():
            p = f"{server}:{name}.{k}"
            if k == "name":
                out.append(("manifest_structure", p, v))
            elif k in _FREE_TEXT_KEYS and isinstance(v, str):
                out.append(("manifest_free_text", p, v))
            else:
                walk(v, p, k)
    return out


@dataclass
class Sources:
    """Every text a literal could come from, as (class, location, text)."""

    texts: list[tuple[str, str, str]] = field(default_factory=list)

    @classmethod
    def from_files(cls, *, intent: Path, trusted_schemas: list[Path], generated_schemas: list[Path],
                   manifests: dict[str, Path]) -> "Sources":
        texts = [("intent", Path(intent).name, Path(intent).read_text())]
        texts += [("trusted_schema", Path(p).name, Path(p).read_text()) for p in trusted_schemas]
        texts += [("generated_schema", Path(p).name, Path(p).read_text()) for p in generated_schemas]
        for server, path in manifests.items():
            texts += _manifest_leaves(server, json.loads(Path(path).read_text()))
        return cls(texts)


def _occurs(token: str, text: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", text) is not None


def provenance(policy: Path, sources: Sources) -> list[dict]:
    """One row per distinct literal: {literal, kind, occurrences, sources: {class: [locations]}}."""
    lits = extract_literals(policy)
    rows = {}
    for lit in lits:
        if lit.text in rows:
            rows[lit.text]["occurrences"] += 1
            continue
        found: dict[str, list[str]] = {}
        if lit.tokens:  # an empty string or a pure-wildcard pattern occurs nowhere by definition
            for cls_, where, text in sources.texts:
                if all(_occurs(t, text) for t in lit.tokens):
                    found.setdefault(cls_, [])
                    if where not in found[cls_]:
                        found[cls_].append(where)
        rows[lit.text] = {"literal": lit.text, "kind": lit.kind, "occurrences": 1,
                          "sources": {c: found[c] for c in CLASSES if c in found}}
    return list(rows.values())
