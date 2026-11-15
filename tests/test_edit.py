"""pgi.mutators.edit: one benign, named edit to a copy of an MCP manifest, with exact provenance. Pure, no LLM.

Contract under test:
  * `apply(manifest, spec)` deep-copies; the argument is never mutated.
  * exactly one semantic edit per call: outside the targeted tool nothing changes, and inside it only the
    node at `spec.path` changes.
  * `EditRecord.before` / `.after` are the node at `spec.path` before and after, exact enough that
    `replay(original, record)` rebuilds the mutated manifest.
  * `rename_param` keeps required-ness unless the caller says `compound=True`; a bare rename that leaves a
    dangling `required` entry is two edits (rename + silent optional), so asking for it implicitly raises.
  * `$ref` / `$defs` are never introduced; `add_key` refuses in-spec keys (those belong to another channel).
Paths are dotted and relative to the tool object ("" is the tool itself); list indices are integers.
"""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from pgi.mutators.edit import (CHANNELS, JSON_SCHEMA_KEYWORDS, MCP_TOOL_FIELDS, OPS, OUT_OF_SPEC_DENYLIST, EditError,
                               EditRecord, EditSpec, apply, replay)

ROOT = Path(__file__).resolve().parents[1]
WO = ROOT / "domains" / "assetopsbench" / "manifests" / "wo.tools.json"
CLOSE = "close_workorder"
MINE = "get_my_assigned_workorders"
PROPS = "inputSchema.properties"


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def _tool(manifest: dict, name: str) -> dict:
    return next(t for t in manifest["tools"] if t["name"] == name)


def _node(tool: dict, path: str):
    node = tool
    for seg in [s for s in path.split(".") if s]:
        node = node[int(seg)] if isinstance(node, list) else node[seg]
    return node


def _changed(a, b, path=""):
    """Dotted paths where two JSON trees differ (lists compared by index)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return [p for k in sorted(set(a) | set(b)) for p in _changed(a.get(k, ...), b.get(k, ...), f"{path}.{k}" if path else k)]
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [p for i, (u, v) in enumerate(zip(a, b)) for p in _changed(u, v, f"{path}.{i}")]
    return [] if a == b else [path]


@pytest.fixture
def wo() -> dict:
    return json.loads(WO.read_text())


# Every benign-restrictive op the engine offers, as a spec on the pinned wo manifest. These feed the
# parametrized contract tests (immutability, single edit, provenance round-trip).
SPECS = {
    "append_restriction.tool": EditSpec(CLOSE, "", "text", "append_restriction", "Only for work orders at site MAIN."),
    "append.tool_description": EditSpec(CLOSE, "", "text", "append", {"field": "description", "text": "Only MAIN."}),
    "append.param_title": EditSpec(CLOSE, f"{PROPS}.site_id", "text", "append", {"field": "title", "text": "(MAIN only)"}),
    "set.tool_title": EditSpec(CLOSE, "", "text", "set", {"field": "title", "text": "Close (MAIN)"}),
    "set.tool_description": EditSpec(CLOSE, "", "text", "set", {"field": "description", "text": "Close a MAIN work order."}),
    "set.param_description": EditSpec(CLOSE, f"{PROPS}.site_id", "text", "set", {"field": "description", "text": "Must be MAIN."}),
    "set.param_title": EditSpec(CLOSE, f"{PROPS}.site_id", "text", "set", {"field": "title", "text": "Site (MAIN)"}),
    "add_enum": EditSpec(CLOSE, f"{PROPS}.site_id", "structure", "add_enum", ["MAIN", "NORTH"]),
    "rename_param": EditSpec(CLOSE, "inputSchema", "structure", "rename_param", {"old": "site_id", "new": "site"}),
    "rename_param.compound": EditSpec(CLOSE, "inputSchema", "structure", "rename_param",
                                      {"old": "site_id", "new": "site"}, compound=True),
    "change_type": EditSpec(CLOSE, f"{PROPS}.actual_hours", "structure", "change_type", "integer"),
    "set_required.off": EditSpec(CLOSE, "inputSchema", "structure", "set_required", {"name": "site_id", "required": False}),
    "set_required.on": EditSpec(MINE, "inputSchema", "structure", "set_required", {"name": "open_only", "required": True}),
    "reorder_anyof": EditSpec(CLOSE, f"{PROPS}.failure_code", "structure", "reorder_anyof", [1, 0]),
    "add_key.tool": EditSpec(CLOSE, "", "out_of_spec", "add_key", {"key": "x-pgi-note", "value": {"benign": True}}),
    "add_key.param": EditSpec(CLOSE, f"{PROPS}.site_id", "out_of_spec", "add_key", {"key": "x-pgi-note", "value": "MAIN only"}),
}


def test_registry_matches_the_agreed_op_list():
    assert CHANNELS == frozenset({"text", "structure", "out_of_spec"})
    assert {op: ch for op, ch in OPS.items()} == {
        "append": "text", "set": "text", "append_restriction": "text",      # append_restriction = alias of append
        "add_enum": "structure", "rename_param": "structure", "change_type": "structure",
        "set_required": "structure", "reorder_anyof": "structure",
        "add_key": "out_of_spec",
    }


# --- text channel: four carriers (tool.description, tool.title, param.title, param.description) -------------

SITE = f"{PROPS}.site_id"
# (level, path, field, present in the pinned wo manifest?)  AOB tools carry a description and a title;
# AOB params carry a title and no description, so param.description is where `set` creates a carrier.
CARRIERS = [("tool", "", "description", True), ("tool", "", "title", True),
            ("param", SITE, "title", True), ("param", SITE, "description", False)]


@pytest.mark.parametrize("level,path,field,present", CARRIERS, ids=lambda x: str(x))
def test_set_creates_or_replaces_any_text_carrier(wo, level, path, field, present):
    mutated, rec = apply(wo, EditSpec(CLOSE, path, "text", "set", {"field": field, "text": "Only for MAIN."}))
    node = _node(_tool(mutated, CLOSE), path)
    assert node[field] == "Only for MAIN."
    assert (field in rec.before) is present
    assert {k: v for k, v in rec.after.items() if k != field} == {k: v for k, v in rec.before.items() if k != field}
    assert rec.carrier == {"level": level, "field": field}
    assert _changed(rec.before, rec.after) == [field]


@pytest.mark.parametrize("level,path,field,present", CARRIERS, ids=lambda x: str(x))
def test_append_needs_the_carrier_to_exist(wo, level, path, field, present):
    s = EditSpec(CLOSE, path, "text", "append", {"field": field, "text": "Only for MAIN."})
    if not present:
        with pytest.raises(EditError, match="absent|no `"):
            apply(wo, s)
        created, _ = apply(wo, EditSpec(CLOSE, path, "text", "set", {"field": field, "text": "Base."}))
        mutated, rec = apply(created, s)
        assert _node(_tool(mutated, CLOSE), path)[field] == "Base. Only for MAIN."
    else:
        mutated, rec = apply(wo, s)
        old = _node(_tool(wo, CLOSE), path)[field]
        assert _node(_tool(mutated, CLOSE), path)[field] == old + " Only for MAIN."
    assert rec.carrier == {"level": level, "field": field} and rec.op == "append"


def test_param_description_can_be_created_where_aob_has_only_a_title(wo):
    mutated, rec = apply(wo, EditSpec(CLOSE, SITE, "text", "set", {"field": "description", "text": "Only MAIN."}))
    assert _node(_tool(mutated, CLOSE), SITE) == {"title": "Site Id", "type": "string", "description": "Only MAIN."}
    assert rec.before == {"title": "Site Id", "type": "string"} and rec.carrier == {"level": "param", "field": "description"}


def test_append_restriction_is_an_alias_of_append_on_the_description(wo):
    a, ra = apply(wo, EditSpec(CLOSE, "", "text", "append_restriction", "Only MAIN."))
    b, rb = apply(wo, EditSpec(CLOSE, "", "text", "append", {"field": "description", "text": "Only MAIN."}))
    c, rc = apply(wo, EditSpec(CLOSE, "", "text", "append", "Only MAIN."))            # a bare string means description
    assert a == b == c and ra.after == rb.after == rc.after
    assert ra.op == "append_restriction" and rb.op == rc.op == "append"                # the record keeps the op as asked
    assert ra.carrier == rb.carrier == rc.carrier == {"level": "tool", "field": "description"}


def test_text_ops_refuse_other_fields_levels_and_no_ops(wo):
    with pytest.raises(EditError, match="field"):
        apply(wo, EditSpec(CLOSE, "", "text", "set", {"field": "name", "text": "x"}))              # not a text carrier
    with pytest.raises(EditError, match="field"):
        apply(wo, EditSpec(CLOSE, "", "text", "append", {"field": "description"}))                 # no text
    with pytest.raises(EditError, match="level|tool or a parameter"):
        apply(wo, EditSpec(CLOSE, "inputSchema", "text", "set", {"field": "title", "text": "x"}))  # neither tool nor param
    with pytest.raises(EditError, match="level|tool or a parameter"):
        apply(wo, EditSpec(CLOSE, f"{PROPS}.failure_code.anyOf.0", "text", "set", {"field": "description", "text": "x"}))
    with pytest.raises(EditError, match="no-op"):
        apply(wo, EditSpec(CLOSE, SITE, "text", "set", {"field": "title", "text": "Site Id"}))     # same text
    assert all(apply(wo, SPECS[k])[1].carrier is None for k in ("add_enum", "set_required.off", "add_key.tool"))


# --- contract: immutability, single edit, provenance ---------------------------------------------------------

@pytest.mark.parametrize("name", sorted(SPECS))
def test_apply_never_mutates_its_input(wo, name):
    before = _sha(wo)
    mutated, _ = apply(wo, SPECS[name])
    assert _sha(wo) == before
    assert _sha(wo) == _sha(json.loads(WO.read_text()))     # and equals the pinned file, so nothing leaked
    assert _sha(mutated) != before


@pytest.mark.parametrize("name", sorted(SPECS))
def test_apply_changes_only_the_targeted_node(wo, name):
    spec = SPECS[name]
    mutated, rec = apply(wo, spec)
    others = [t["name"] for t in wo["tools"] if t["name"] != spec.tool]
    assert [_tool(mutated, n) for n in others] == [_tool(wo, n) for n in others]
    assert [t["name"] for t in mutated["tools"]] == [t["name"] for t in wo["tools"]]      # order and names kept
    changed = _changed(_tool(wo, spec.tool), _tool(mutated, spec.tool))
    assert changed, "a no-op is zero edits, not one"
    assert all(p == spec.path or p.startswith(spec.path + ".") or spec.path == "" for p in changed), changed


@pytest.mark.parametrize("name", sorted(SPECS))
def test_record_is_exact_provenance_and_replays(wo, name):
    spec = SPECS[name]
    mutated, rec = apply(wo, spec)
    assert (rec.tool, rec.path, rec.channel, rec.op, rec.compound) == \
        (spec.tool, spec.path, spec.channel, spec.op, spec.compound)
    assert rec.before == _node(_tool(wo, spec.tool), spec.path)
    assert rec.after == _node(_tool(mutated, spec.tool), spec.path)
    assert rec.before != rec.after
    assert replay(wo, rec) == mutated                      # before/after alone rebuild the mutated manifest
    assert _sha(wo) == _sha(json.loads(WO.read_text()))    # replay copies too
    rt = EditRecord.from_dict(json.loads(json.dumps(rec.as_dict())))
    assert rt == rec


def test_record_before_and_after_are_detached_copies(wo):
    mutated, rec = apply(wo, SPECS["add_enum"])
    _node(_tool(mutated, CLOSE), f"{PROPS}.site_id")["enum"].append("WEST")
    assert rec.after["enum"] == ["MAIN", "NORTH"]
    _tool(wo, CLOSE)["inputSchema"]["properties"]["site_id"]["title"] = "x"
    assert rec.before["title"] == "Site Id"


def test_replay_refuses_a_manifest_whose_node_is_not_the_recorded_before(wo):
    _, rec = apply(wo, SPECS["add_enum"])
    other, _ = apply(wo, SPECS["change_type"])     # same tool, different node, so `before` still matches...
    assert replay(other, rec)                      # ...and replay composes
    drifted, _ = apply(wo, SPECS["set_required.off"])
    _tool(drifted, CLOSE)["inputSchema"]["properties"]["site_id"]["title"] = "Site"   # the recorded node drifted
    with pytest.raises(EditError, match="before"):
        replay(drifted, rec)


# --- text channel -------------------------------------------------------------------------------------------

def test_append_restriction_appends_one_sentence_to_the_tool_description(wo):
    mutated, rec = apply(wo, SPECS["append_restriction.tool"])
    old = _tool(wo, CLOSE)["description"]
    assert _tool(mutated, CLOSE)["description"] == old + " Only for work orders at site MAIN."
    assert rec.before["description"] == old and rec.after["description"].startswith(old)
    assert {k: v for k, v in rec.after.items() if k != "description"} == {k: v for k, v in rec.before.items() if k != "description"}


def test_append_restriction_needs_an_existing_description(wo):
    # AOB params carry a `title` but no `description`; creating one is a different edit (a new key), not an append.
    with pytest.raises(EditError, match="description"):
        apply(wo, EditSpec(CLOSE, f"{PROPS}.site_id", "text", "append_restriction", "Only MAIN."))
    with pytest.raises(EditError, match="sentence"):
        apply(wo, EditSpec(CLOSE, "", "text", "append_restriction", ""))


# --- structure channel --------------------------------------------------------------------------------------

def test_add_enum_adds_the_values_and_nothing_else(wo):
    mutated, rec = apply(wo, SPECS["add_enum"])
    site = _node(_tool(mutated, CLOSE), f"{PROPS}.site_id")
    assert site == {"title": "Site Id", "type": "string", "enum": ["MAIN", "NORTH"]}
    assert rec.before == {"title": "Site Id", "type": "string"} and rec.after == site


def test_add_enum_refusals(wo):
    for value in ([], ["MAIN", "MAIN"], [{"not": "scalar"}], [1, 2]):          # empty, duplicate, non-scalar, type mismatch
        with pytest.raises(EditError):
            apply(wo, EditSpec(CLOSE, f"{PROPS}.site_id", "structure", "add_enum", value))
    with pytest.raises(EditError, match="anyOf"):                             # a union: target a branch instead
        apply(wo, EditSpec(CLOSE, f"{PROPS}.failure_code", "structure", "add_enum", ["A"]))
    branch, _ = apply(wo, EditSpec(CLOSE, f"{PROPS}.failure_code.anyOf.0", "structure", "add_enum", ["A", "B"]))
    assert _node(_tool(branch, CLOSE), f"{PROPS}.failure_code.anyOf.0") == {"type": "string", "enum": ["A", "B"]}
    once, _ = apply(wo, SPECS["add_enum"])
    with pytest.raises(EditError, match="enum"):                              # already has one
        apply(once, SPECS["add_enum"])


def test_rename_param_keeps_the_field_required(wo):
    mutated, rec = apply(wo, SPECS["rename_param"])
    schema = _tool(mutated, CLOSE)["inputSchema"]
    assert list(schema["properties"]) == ["actual_hours", "failure_code", "resolution_notes", "site", "wonum"]
    assert schema["properties"]["site"] == _tool(wo, CLOSE)["inputSchema"]["properties"]["site_id"]
    assert schema["required"] == ["wonum", "site"]           # same slot, new name: required-ness unchanged
    assert rec.compound is False
    assert _changed(rec.before, rec.after) == ["properties.site", "properties.site_id", "required.1"]


def test_a_bare_rename_would_flip_required_so_it_must_be_asked_for_as_compound(wo):
    # The guard is doing real work: without it the dangling `required` entry makes the renamed field optional.
    bare, rec = apply(wo, SPECS["rename_param.compound"])
    schema = _tool(bare, CLOSE)["inputSchema"]
    assert "site" in schema["properties"] and "site_id" not in schema["properties"]
    assert schema["required"] == ["wonum", "site_id"]        # dangling: the generator silently ignores it
    assert rec.compound is True
    assert _changed(rec.before, rec.after) == ["properties.site", "properties.site_id"]
    # Asking for the bare rename without owning up to it is refused.
    with pytest.raises(EditError, match="compound"):
        apply(wo, EditSpec(CLOSE, "inputSchema", "structure", "rename_param",
                           {"old": "site_id", "new": "site", "update_required": False}))


def test_rename_of_an_optional_param_is_never_compound(wo):
    mutated, rec = apply(wo, EditSpec(MINE, "inputSchema", "structure", "rename_param", {"old": "open_only", "new": "open"}))
    assert _tool(mutated, MINE)["inputSchema"]["required"] == ["labor_code"] and rec.compound is False
    with pytest.raises(EditError, match="compound"):          # nothing to dangle, so the flag would be a lie
        apply(wo, EditSpec(MINE, "inputSchema", "structure", "rename_param", {"old": "open_only", "new": "open"}, compound=True))


def test_rename_param_refusals(wo):
    for value in ({"old": "nope", "new": "x"}, {"old": "site_id", "new": "wonum"}, {"old": "site_id", "new": "site_id"}):
        with pytest.raises(EditError):
            apply(wo, EditSpec(CLOSE, "inputSchema", "structure", "rename_param", value))


def test_compound_is_only_meaningful_for_rename_param(wo):
    for name in ("add_enum", "change_type", "set_required.off", "reorder_anyof", "add_key.tool", "append_restriction.tool"):
        s = SPECS[name]
        with pytest.raises(EditError, match="compound"):
            apply(wo, EditSpec(s.tool, s.path, s.channel, s.op, s.value, compound=True))


def test_change_type(wo):
    mutated, rec = apply(wo, SPECS["change_type"])
    assert _node(_tool(mutated, CLOSE), f"{PROPS}.actual_hours") == {"default": 0.0, "title": "Actual Hours", "type": "integer"}
    assert rec.before["type"] == "number" and rec.after["type"] == "integer"
    with pytest.raises(EditError, match="no-op"):
        apply(wo, EditSpec(CLOSE, f"{PROPS}.actual_hours", "structure", "change_type", "number"))
    with pytest.raises(EditError, match="anyOf"):                       # unions have no top-level type
        apply(wo, EditSpec(CLOSE, f"{PROPS}.failure_code", "structure", "change_type", "integer"))
    with pytest.raises(EditError, match="type"):
        apply(wo, EditSpec(CLOSE, f"{PROPS}.actual_hours", "structure", "change_type", "float"))


def test_set_required(wo):
    off, rec = apply(wo, SPECS["set_required.off"])
    assert _tool(off, CLOSE)["inputSchema"]["required"] == ["wonum"]
    assert rec.before["required"] == ["wonum", "site_id"]
    on, rec = apply(wo, SPECS["set_required.on"])
    assert _tool(on, MINE)["inputSchema"]["required"] == ["labor_code", "open_only"]
    assert _tool(on, MINE)["inputSchema"]["properties"] == _tool(wo, MINE)["inputSchema"]["properties"]   # default untouched
    with pytest.raises(EditError, match="no-op"):
        apply(wo, EditSpec(CLOSE, "inputSchema", "structure", "set_required", {"name": "site_id", "required": True}))
    with pytest.raises(EditError):
        apply(wo, EditSpec(CLOSE, "inputSchema", "structure", "set_required", {"name": "nope", "required": True}))


def test_reorder_anyof(wo):
    mutated, rec = apply(wo, SPECS["reorder_anyof"])
    assert _node(_tool(mutated, CLOSE), f"{PROPS}.failure_code.anyOf") == [{"type": "null"}, {"type": "string"}]
    assert rec.before["anyOf"] == [{"type": "string"}, {"type": "null"}] and rec.before["default"] == rec.after["default"]
    for value in ([0, 1], [0, 0], [0], [2, 1]):                             # identity, not a permutation
        with pytest.raises(EditError):
            apply(wo, EditSpec(CLOSE, f"{PROPS}.failure_code", "structure", "reorder_anyof", value))
    with pytest.raises(EditError, match="anyOf"):
        apply(wo, EditSpec(CLOSE, f"{PROPS}.site_id", "structure", "reorder_anyof", [1, 0]))


# --- out_of_spec channel ------------------------------------------------------------------------------------

def test_add_key_on_tool_and_param(wo):
    mutated, rec = apply(wo, SPECS["add_key.tool"])
    assert _tool(mutated, CLOSE)["x-pgi-note"] == {"benign": True}
    assert set(rec.after) - set(rec.before) == {"x-pgi-note"}
    mutated, rec = apply(wo, SPECS["add_key.param"])
    assert _node(_tool(mutated, CLOSE), f"{PROPS}.site_id") == {"title": "Site Id", "type": "string", "x-pgi-note": "MAIN only"}


def test_add_key_never_introduces_ref_or_defs(wo):
    for key, value in (("$ref", "#/$defs/Site"), ("$defs", {"Site": {"type": "string"}}),
                       ("x-pgi-note", {"$ref": "#/x"}), ("x-pgi-note", [{"deep": {"$defs": {}}}])):
        with pytest.raises(EditError, match=r"\$ref|\$defs"):
            apply(wo, EditSpec(CLOSE, f"{PROPS}.site_id", "out_of_spec", "add_key", {"key": key, "value": value}))


@pytest.mark.parametrize("key,value", [("enum", ["MAIN"]), ("format", "date-time"), ("type", "string"), ("required", []),
                                       ("items", {"type": "string"}), ("anyOf", [{"type": "string"}]),
                                       ("description", "x"), ("title", "x"), ("default", "MAIN"), ("pattern", "^M"),
                                       ("name", "x"), ("inputSchema", {}), ("annotations", {})])
def test_add_key_refuses_each_in_spec_key(wo, key, value):
    assert key in OUT_OF_SPEC_DENYLIST
    with pytest.raises(EditError, match="in-spec"):
        apply(wo, EditSpec(CLOSE, "", "out_of_spec", "add_key", {"key": key, "value": value}))
    with pytest.raises(EditError, match="in-spec"):
        apply(wo, EditSpec(CLOSE, f"{PROPS}.site_id", "out_of_spec", "add_key", {"key": key, "value": value}))


def test_denylist_is_an_explicit_documented_constant():
    assert OUT_OF_SPEC_DENYLIST == JSON_SCHEMA_KEYWORDS | MCP_TOOL_FIELDS
    assert {"$ref", "$defs", "type", "enum", "format", "required", "properties", "items", "anyOf", "oneOf", "allOf",
            "description", "title", "default"} <= JSON_SCHEMA_KEYWORDS
    assert {"name", "title", "description", "inputSchema", "outputSchema", "annotations"} <= MCP_TOOL_FIELDS
    assert "x-pgi-note" not in OUT_OF_SPEC_DENYLIST


def test_add_key_refuses_existing_keys(wo):
    once, _ = apply(wo, SPECS["add_key.param"])
    with pytest.raises(EditError, match="exists"):
        apply(once, SPECS["add_key.param"])


# --- spec validation ----------------------------------------------------------------------------------------

def test_spec_errors(wo):
    with pytest.raises(EditError, match="channel"):                       # op/channel mismatch
        apply(wo, EditSpec(CLOSE, f"{PROPS}.site_id", "text", "add_enum", ["MAIN"]))
    with pytest.raises(EditError, match="channel"):
        apply(wo, EditSpec(CLOSE, "", "secret", "append_restriction", "x"))
    with pytest.raises(EditError, match="op"):
        apply(wo, EditSpec(CLOSE, "", "text", "shout", "x"))
    with pytest.raises(EditError, match="tool"):
        apply(wo, EditSpec("no_such_tool", "", "text", "append_restriction", "x"))
    with pytest.raises(EditError, match="path"):
        apply(wo, EditSpec(CLOSE, f"{PROPS}.nope", "structure", "add_enum", ["MAIN"]))
    with pytest.raises(EditError, match="tools"):
        apply({"result": wo}, SPECS["add_enum"])                          # only the pinned `{"tools": [...]}` form


def test_spec_and_record_are_frozen(wo):
    _, rec = apply(wo, SPECS["add_enum"])
    with pytest.raises(Exception):
        rec.tool = "x"
    with pytest.raises(Exception):
        SPECS["add_enum"].value = []
