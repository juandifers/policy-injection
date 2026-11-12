"""Is a symcc counterexample producible by a real tool call?

symcc quantifies over every well-typed request, including some that the request builder can never
emit. This module checks a counterexample against the encoding of cedar-policy-mcp-schema-generator
0.7.0 (`request.rs`, `validation.rs`, tag v0.7.0) for values under `context.input`:

  R1  union record (all attributes `typeChoice<N>`, all optional): exactly one branch present
  R2  `<root>::Null` entity: id is "null"
  R3  `<root>::Number` entity: id is a JSON number literal
  R4  `<root>::Float` entity: id is Rust `{:?}` float text
  R5  opaque object entity (entity type in a sub-namespace of root, not an enum): id is a v4 UUID
  R6  String / Long / Bool / Set / enum entity / absent optional attribute: always realizable
  R7  context outside `input` (trusted fields our gate supplies): assumed realizable if well-typed
  R8  principal, resource and any other entity id: always realizable

`classify` turns one `sym.implies_in` result into holds / does_not_hold / undetermined. symcc returns
a single counterexample per environment, so an unrealizable one leaves the question undetermined.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pgi.oracle import sym

_TYPECHOICE = re.compile(r"typeChoice\d+")
_JSON_NUMBER = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?")
_RUST_FLOAT = re.compile(r"-?([0-9]+\.[0-9]+|[0-9]+(\.[0-9]+)?e-?[0-9]+|inf)|NaN")
_UUID4 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


@dataclass(frozen=True)
class Violation:
    """One value the request builder cannot produce."""

    rule: str
    path: str
    detail: str


@dataclass(frozen=True)
class Report:
    """Realizability of one counterexample."""

    realizable: bool
    violations: tuple[Violation, ...]


@dataclass(frozen=True)
class Classification:
    """One symcc implication result, with realizability taken into account."""

    status: str  # "holds" | "does_not_hold" | "undetermined"
    violations: tuple[Violation, ...]
    counterexample: dict | None


@lru_cache(maxsize=16)
def _schema(path: str) -> tuple[dict, dict, frozenset, frozenset]:
    """(actions by UID, common types, enum entity types, object entity types) from the resolved JSON schema."""
    out = subprocess.run(["cedar", "translate-schema", "--direction", "cedar-to-json-with-resolved-types",
                          "--schema", path], capture_output=True, text=True)
    if out.returncode != 0:
        raise sym.SymccError(f"translate-schema failed for {path}: {out.stderr}")
    doc = json.loads(out.stdout)
    q = lambda ns, n: f"{ns}::{n}" if ns else n
    actions = {f'{q(ns, "Action")}::{json.dumps(a)}': body for ns, b in doc.items() for a, body in b.get("actions", {}).items()}
    common = {q(ns, n): t for ns, b in doc.items() for n, t in b.get("commonTypes", {}).items()}
    enums = frozenset(q(ns, n) for ns, b in doc.items() for n, e in b.get("entityTypes", {}).items() if "enum" in e)
    nested = frozenset(q(ns, n) for ns, b in doc.items() for n in b.get("entityTypes", {}) if "::" in ns)
    return actions, common, enums, nested - enums


def _resolve(decl: dict, common: dict) -> dict:
    """Follow common-type references to a concrete type."""
    while decl.get("type") in common:
        decl = common[decl["type"]]
    return decl


def _entity(uid: dict, path: str, root: str, enums: frozenset, objects: frozenset) -> Violation | None:
    """R2-R5 and R8 for one entity value under context.input."""
    etype, eid = uid["type"], uid["id"]
    checks = {f"{root}::Null": ("R2", eid == "null", 'id must be "null"'),
              f"{root}::Number": ("R3", bool(_JSON_NUMBER.fullmatch(eid)), "id must be a JSON number literal"),
              f"{root}::Float": ("R4", bool(_RUST_FLOAT.fullmatch(eid)), "id must be Rust float text")}
    if etype in checks:
        rule, ok, why = checks[etype]
    elif etype in objects:
        rule, ok, why = "R5", bool(_UUID4.fullmatch(eid)), "object entity id must be a fresh v4 UUID"
    else:
        return None  # enum entities (R6, checked by the schema) and every other entity (R8)
    return None if ok else Violation(rule, path, f"{etype}::{json.dumps(eid)}: {why}")


def _walk(value: object, decl: dict, path: str, in_input: bool, ctx: tuple, out: list[Violation]) -> None:
    """Check one value against its declared type, recursing through records and sets."""
    common, root, enums, objects = ctx
    decl = _resolve(decl, common)
    kind = decl.get("type")
    if kind == "Record" and isinstance(value, dict):
        attrs = decl.get("attributes", {})
        is_union = attrs and all(_TYPECHOICE.fullmatch(k) and not a.get("required", True) for k, a in attrs.items())
        if in_input and is_union and sum(k in value for k in attrs) != 1:
            out.append(Violation("R1", path, f"union record with {sum(k in value for k in attrs)} branches set"))
        for k, v in value.items():
            if k in attrs:
                _walk(v, attrs[k], f"{path}.{k}", in_input or path == "context" and k == "input", ctx, out)
    elif kind == "Set" and isinstance(value, list):
        for i, v in enumerate(value):
            _walk(v, decl["element"], f"{path}[{i}]", in_input, ctx, out)
    elif kind == "Entity" and isinstance(value, dict) and in_input:
        if (v := _entity(value["__entity"], path, root, enums, objects)) is not None:
            out.append(v)


def check(cex: sym.Counterexample, schema: Path) -> Report:
    """Which values of a parsed counterexample the request builder could not have produced."""
    actions, common, enums, objects = _schema(str(schema))
    act = cex.request["action"]
    uid = f'{act["type"]}::{json.dumps(act["id"])}'
    if uid not in actions:
        raise sym.SymccError(f"counterexample action {uid} not in {schema}")
    root = act["type"].rpartition("::")[0]
    out: list[Violation] = []
    _walk(cex.request["context"], actions[uid]["appliesTo"]["context"], "context", False, (common, root, enums, objects), out)
    return Report(not out, tuple(out))


def classify(result: str, schema: Path) -> Classification:
    """holds (VERIFIED), does_not_hold (realizable counterexample) or undetermined (unrealizable one)."""
    if result == sym.VERIFIED:
        return Classification("holds", (), None)
    cex = sym.parse_counterexample(result)
    report = check(cex, schema)
    status = "does_not_hold" if report.realizable else "undetermined"
    return Classification(status, report.violations, {"request": cex.request, "entities": cex.entities})
