"""One benign, named edit to a copy of an MCP manifest, with exact provenance. Pure and domain-agnostic; no LLM.

An `EditSpec` names one tool, one node inside it (a dotted path relative to the tool object; "" is the tool,
list indices are integers), the channel the edit travels on and the op:

  channel      op                   value                                    node at `path`
  text         append_restriction   sentence                                 anything with a `description`
  structure    add_enum             [scalar, ...]                            a typed node (not a union)
  structure    rename_param         {"old", "new"[, "update_required"]}      an object schema (`properties`)
  structure    change_type          JSON Schema primitive type name          a typed node (not a union)
  structure    set_required         {"name", "required": bool}               an object schema
  structure    reorder_anyof        permutation of branch indices            a node with `anyOf`
  out_of_spec  add_key              {"key", "value"}                         any object

`apply` deep-copies the manifest and performs exactly one semantic edit (a no-op raises). The `EditRecord`
it returns holds the node before and after, exact enough that `replay` rebuilds the mutated manifest.

rename_param keeps the field's required-ness by renaming its `required` entry in place. A bare rename leaves
a dangling entry that the schema generator silently ignores, so the field becomes optional: two edits in one.
It is available only with `compound=True`, and only when the field was required (otherwise the flag lies).

$ref / $defs are never introduced, and add_key refuses keys the schema generator or the text channel owns.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

CHANNELS = frozenset({"text", "structure", "out_of_spec"})
OPS: dict[str, str] = {               # op -> channel
    "append_restriction": "text",
    "add_enum": "structure",
    "rename_param": "structure",
    "change_type": "structure",
    "set_required": "structure",
    "reorder_anyof": "structure",
    "add_key": "out_of_spec",
}
JSON_TYPES = frozenset({"string", "integer", "number", "boolean", "array", "object", "null"})
FORBIDDEN_KEYS = frozenset({"$ref", "$defs"})
# Keys add_key refuses: the generator reads the structural ones (a mislabelled structure edit), and the text
# channel owns the free-text ones. Both have their own op or channel.
IN_SPEC_KEYS = frozenset({
    "type", "enum", "const", "format", "required", "anyOf", "oneOf", "allOf", "not", "properties", "items",
    "prefixItems", "additionalProperties", "patternProperties", "definitions", "if", "then", "else",
    "name", "inputSchema", "outputSchema", "annotations",
    "title", "description", "default", "pattern", "maxLength", "minLength", "minimum", "maximum", "examples",
})
SCALARS = (str, int, float, bool)
_TYPE_OF_SCALAR = {"string": str, "integer": int, "number": (int, float), "boolean": bool}


class EditError(Exception):
    """The spec is malformed, its target is missing, or the edit would be a no-op or more than one edit."""


@dataclass(frozen=True)
class EditSpec:
    tool: str
    path: str
    channel: str
    op: str
    value: Any = None
    compound: bool = False

    def as_dict(self) -> dict:
        return copy.deepcopy(asdict(self))


@dataclass(frozen=True)
class EditRecord:
    """Exact, diffable provenance: the node at `path` inside `tool`, before and after the edit."""
    tool: str
    path: str
    channel: str
    op: str
    before: Any
    after: Any
    compound: bool = field(default=False)

    def as_dict(self) -> dict:
        return copy.deepcopy(asdict(self))

    @classmethod
    def from_dict(cls, d: dict) -> EditRecord:
        return cls(**copy.deepcopy(d))


# --- addressing ----------------------------------------------------------------------------------------------

def _segments(path: str) -> list[str | int]:
    return [int(s) if s.isdigit() else s for s in path.split(".") if s]


def _tool(manifest: dict, name: str) -> dict:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("tools"), list):
        raise EditError('manifest must be the pinned {"tools": [...]} form')
    for t in manifest["tools"]:
        if isinstance(t, dict) and t.get("name") == name:
            return t
    raise EditError(f"no tool {name!r} in the manifest")


def _node(tool: dict, path: str) -> Any:
    node = tool
    for seg in _segments(path):
        try:
            node = node[seg]
        except (KeyError, IndexError, TypeError):
            raise EditError(f"path {path!r} not found in the tool") from None
    return node


def _set_node(tool: dict, path: str, value: Any) -> None:
    segs = _segments(path)
    if not segs:
        tool.clear()
        tool.update(value)
        return
    parent = _node(tool, ".".join(map(str, segs[:-1])))
    parent[segs[-1]] = value


def _count_forbidden(obj: Any) -> int:
    if isinstance(obj, dict):
        return sum(k in FORBIDDEN_KEYS for k in obj) + sum(_count_forbidden(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(_count_forbidden(v) for v in obj)
    return 0


def _need(spec: EditSpec, keys: tuple[str, ...]) -> dict:
    v = spec.value
    if not isinstance(v, dict) or any(k not in v for k in keys):
        raise EditError(f"{spec.op} needs a value with keys {keys}, got {v!r}")
    return v


def _object_schema(node: Any, spec: EditSpec) -> dict:
    if not isinstance(node, dict) or not isinstance(node.get("properties"), dict):
        raise EditError(f"{spec.op}: path {spec.path!r} is not an object schema with `properties`")
    return node


def _typed(node: Any, spec: EditSpec) -> dict:
    if not isinstance(node, dict):
        raise EditError(f"{spec.op}: path {spec.path!r} is not an object")
    if "anyOf" in node or "oneOf" in node:
        raise EditError(f"{spec.op}: {spec.path!r} is a union (anyOf); target one branch, e.g. {spec.path}.anyOf.0")
    if not isinstance(node.get("type"), str):
        raise EditError(f"{spec.op}: {spec.path!r} has no `type`")
    return node


# --- ops: each edits `node` (already a private copy) in place and returns nothing ----------------------------------

def _append_restriction(node: Any, spec: EditSpec) -> None:
    sentence = spec.value
    if not isinstance(sentence, str) or not sentence.strip():
        raise EditError("append_restriction needs a non-empty sentence")
    if not isinstance(node, dict) or not isinstance(node.get("description"), str):
        raise EditError(f"{spec.path!r} has no `description` to append to (creating one is a different edit)")
    node["description"] = node["description"] + " " + sentence if node["description"] else sentence


def _add_enum(node: Any, spec: EditSpec) -> None:
    node = _typed(node, spec)
    values = spec.value
    if not isinstance(values, list) or not values:
        raise EditError("add_enum needs a non-empty list of values")
    if any(not isinstance(v, SCALARS) for v in values):
        raise EditError("add_enum values must be JSON scalars")
    if len(set(map(repr, values))) != len(values):
        raise EditError("add_enum values must be distinct")
    want = _TYPE_OF_SCALAR.get(node["type"])
    if want is None or any(not isinstance(v, want) or (isinstance(v, bool) and node["type"] != "boolean") for v in values):
        raise EditError(f"add_enum values {values!r} do not match type {node['type']!r}")
    if "enum" in node:
        raise EditError(f"{spec.path!r} already has an enum")
    node["enum"] = list(values)


def _rename_param(node: Any, spec: EditSpec) -> None:
    schema = _object_schema(node, spec)
    v = _need(spec, ("old", "new"))
    old, new, update_required = v["old"], v["new"], v.get("update_required", True)
    props = schema["properties"]
    if old not in props:
        raise EditError(f"no parameter {old!r} to rename")
    if new in props:
        raise EditError(f"parameter {new!r} already exists")
    if new == old or not isinstance(new, str) or not new:
        raise EditError("rename_param: new name must be a different non-empty string (no-op otherwise)")
    required = schema.get("required") or []
    was_required = old in required
    if spec.compound and not was_required:
        raise EditError(f"compound=True but {old!r} is not required, so a bare rename is not compound")
    if not update_required and not spec.compound:
        raise EditError("a rename that leaves a dangling `required` entry is two edits (rename + silent optional); "
                        "set compound=True to ask for it explicitly")
    schema["properties"] = {new if k == old else k: val for k, val in props.items()}
    if was_required and not spec.compound:
        schema["required"] = [new if r == old else r for r in required]


def _change_type(node: Any, spec: EditSpec) -> None:
    node = _typed(node, spec)
    new = spec.value
    if new not in JSON_TYPES:
        raise EditError(f"change_type: {new!r} is not a JSON Schema type {sorted(JSON_TYPES)}")
    if node["type"] == new:
        raise EditError(f"change_type: {spec.path!r} already has type {new!r} (no-op)")
    node["type"] = new


def _set_required(node: Any, spec: EditSpec) -> None:
    schema = _object_schema(node, spec)
    v = _need(spec, ("name", "required"))
    name, want = v["name"], v["required"]
    if name not in schema["properties"]:
        raise EditError(f"no parameter {name!r}")
    if not isinstance(want, bool):
        raise EditError("set_required: `required` must be a bool")
    required = list(schema.get("required") or [])
    if (name in required) == want:
        raise EditError(f"set_required: {name!r} is already {'required' if want else 'optional'} (no-op)")
    schema["required"] = required + [name] if want else [r for r in required if r != name]


def _reorder_anyof(node: Any, spec: EditSpec) -> None:
    if not isinstance(node, dict) or not isinstance(node.get("anyOf"), list):
        raise EditError(f"reorder_anyof: {spec.path!r} has no anyOf")
    branches, order = node["anyOf"], spec.value
    if not isinstance(order, list) or sorted(order) != list(range(len(branches))):
        raise EditError(f"reorder_anyof: {order!r} is not a permutation of {list(range(len(branches)))}")
    if order == list(range(len(branches))):
        raise EditError("reorder_anyof: identity permutation (no-op)")
    node["anyOf"] = [branches[i] for i in order]


def _add_key(node: Any, spec: EditSpec) -> None:
    if not isinstance(node, dict):
        raise EditError(f"add_key: {spec.path!r} is not an object")
    v = _need(spec, ("key", "value"))
    key = v["key"]
    if not isinstance(key, str) or not key:
        raise EditError("add_key: key must be a non-empty string")
    if key in FORBIDDEN_KEYS or _count_forbidden(v["value"]):
        raise EditError("add_key must not introduce $ref or $defs")
    if key in IN_SPEC_KEYS:
        raise EditError(f"add_key: {key!r} is an in-spec key; use the structure or text channel for it")
    if key in node:
        raise EditError(f"add_key: {key!r} already exists at {spec.path!r}")
    node[key] = copy.deepcopy(v["value"])


_IMPL: dict[str, Callable[[Any, EditSpec], None]] = {
    "append_restriction": _append_restriction,
    "add_enum": _add_enum,
    "rename_param": _rename_param,
    "change_type": _change_type,
    "set_required": _set_required,
    "reorder_anyof": _reorder_anyof,
    "add_key": _add_key,
}


# --- public --------------------------------------------------------------------------------------------------

def apply(manifest: dict, spec: EditSpec) -> tuple[dict, EditRecord]:
    """A deep-copied manifest with exactly one edit applied, and the record of that edit. `manifest` is untouched."""
    if spec.channel not in CHANNELS:
        raise EditError(f"unknown channel {spec.channel!r}; known: {sorted(CHANNELS)}")
    if spec.op not in OPS:
        raise EditError(f"unknown op {spec.op!r}; known: {sorted(OPS)}")
    if OPS[spec.op] != spec.channel:
        raise EditError(f"op {spec.op!r} travels on channel {OPS[spec.op]!r}, not {spec.channel!r}")
    if spec.compound and spec.op != "rename_param":
        raise EditError("compound=True is only meaningful for rename_param")
    _tool(manifest, spec.tool)                      # validate on the original before copying
    mutated = copy.deepcopy(manifest)
    tool = _tool(mutated, spec.tool)
    forbidden_before = _count_forbidden(tool)
    before = copy.deepcopy(_node(tool, spec.path))
    _IMPL[spec.op](_node(tool, spec.path), spec)
    after = copy.deepcopy(_node(tool, spec.path))
    if after == before:
        raise EditError(f"{spec.op} at {spec.path!r} changed nothing (no-op)")
    if _count_forbidden(tool) != forbidden_before:
        raise EditError("the edit introduced $ref or $defs")
    return mutated, EditRecord(spec.tool, spec.path, spec.channel, spec.op, before, after, spec.compound)


def replay(manifest: dict, record: EditRecord) -> dict:
    """A deep copy of `manifest` with the recorded node replaced by `record.after`; the node must equal `record.before`."""
    _tool(manifest, record.tool)
    mutated = copy.deepcopy(manifest)
    tool = _tool(mutated, record.tool)
    if _node(tool, record.path) != record.before:
        raise EditError(f"node at {record.path!r} of {record.tool!r} is not the recorded `before`")
    _set_node(tool, record.path, copy.deepcopy(record.after))
    return mutated
