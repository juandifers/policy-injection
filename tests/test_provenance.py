"""Literal provenance: which input does each literal in a generated policy come from? No LLM.

Synthetic inputs, one distinct literal per source class, plus one literal that occurs nowhere:

    literal              where it is planted
    "ALPHA"              intent
    T::Status::"OKAY"    trusted schema (enum id)
    G::Mode::"FAST"      generated schema (enum id)
    "BLUE"               manifest structure (enum value)
    "ZETA"               manifest free text (a description)
    "OMEGA"              nowhere
    42                   intent
    G::Action::"do_thing"  generated schema (action) AND manifest structure (tool name)
"""

import json
import shutil
from pathlib import Path

import pytest

from pgi.analysis.provenance import Sources, extract_literals, provenance

POLICY = '''
permit (principal, action == G::Action::"do_thing", resource)
when {
  context.a == "ALPHA" && context.b == T::Status::"OKAY" && context.c == G::Mode::"FAST" &&
  context.d == "BLUE" && context.e == "ZETA" && context.f == "OMEGA" && context.n <= 42
};
'''
INTENT = "Only site ALPHA, at most 42 runs. Never use zeta."   # lower-case zeta must not match "ZETA"
TRUSTED = 'namespace T { entity Status enum ["OKAY"]; }\n'
GENERATED = 'namespace G { entity Mode enum ["FAST"]; action "do_thing"; }\n'
MANIFEST = {"tools": [{
    "name": "do_thing", "title": "Do the thing",
    "description": "Set e to the code ZETA. ALPHABET soup.",      # ALPHABET must not match ALPHA
    "inputSchema": {"type": "object", "properties": {
        "d": {"type": "string", "enum": ["BLUE", "GREEN"], "description": "colour"},
        "n": {"type": "integer"}}, "required": ["d"]}}]}


@pytest.fixture(autouse=True)
def _cedar():
    if shutil.which("cedar") is None:
        pytest.skip("cedar CLI not on PATH")


@pytest.fixture
def files(tmp_path):
    p = {"policy": tmp_path / "p.cedar", "intent": tmp_path / "intent.md", "trusted": tmp_path / "trusted.cedarschema",
         "generated": tmp_path / "gen.cedarschema", "manifest": tmp_path / "x.tools.json"}
    p["policy"].write_text(POLICY)
    p["intent"].write_text(INTENT)
    p["trusted"].write_text(TRUSTED)
    p["generated"].write_text(GENERATED)
    p["manifest"].write_text(json.dumps(MANIFEST))
    return p


def by_literal(rows):
    return {r["literal"]: r for r in rows}


def test_extracts_strings_longs_and_entity_ids_from_conditions_and_scope(files):
    lits = {(l.kind, l.text) for l in extract_literals(files["policy"])}
    assert lits == {("entity", 'G::Action::"do_thing"'), ("string", '"ALPHA"'), ("entity", 'T::Status::"OKAY"'),
                    ("entity", 'G::Mode::"FAST"'), ("string", '"BLUE"'), ("string", '"ZETA"'),
                    ("string", '"OMEGA"'), ("long", "42")}


def test_each_source_class_is_found_and_a_literal_can_have_several_or_none(files):
    src = Sources.from_files(intent=files["intent"], trusted_schemas=[files["trusted"]],
                             generated_schemas=[files["generated"]], manifests={"x": files["manifest"]})
    rows = by_literal(provenance(files["policy"], src))
    classes = {lit: sorted(r["sources"]) for lit, r in rows.items()}
    assert classes == {
        '"ALPHA"': ["intent"],
        '42': ["intent"],
        'T::Status::"OKAY"': ["trusted_schema"],
        'G::Mode::"FAST"': ["generated_schema"],
        '"BLUE"': ["manifest_structure"],
        '"ZETA"': ["manifest_free_text"],
        '"OMEGA"': [],
        'G::Action::"do_thing"': ["generated_schema", "manifest_structure"],
    }


def test_manifest_locations_name_the_field(files):
    src = Sources.from_files(intent=files["intent"], trusted_schemas=[files["trusted"]],
                             generated_schemas=[files["generated"]], manifests={"x": files["manifest"]})
    rows = by_literal(provenance(files["policy"], src))
    assert rows['"ZETA"']["sources"]["manifest_free_text"] == ["x:do_thing.description"]
    assert rows['"BLUE"']["sources"]["manifest_structure"] == ["x:do_thing.inputSchema.properties.d.enum[0]"]
    assert rows['G::Action::"do_thing"']["sources"]["manifest_structure"] == ["x:do_thing.name"]


def test_unparseable_policy_raises_a_clear_error(tmp_path, files):
    bad = tmp_path / "bad.cedar"
    bad.write_text("I can't help with that.")
    src = Sources.from_files(intent=files["intent"], trusted_schemas=[], generated_schemas=[], manifests={})
    with pytest.raises(ValueError, match="does not parse"):
        provenance(bad, src)
