"""Phase 2b, A2: what the pinned Dogwood toolchain (dogwood-language 1.1.0 via pydogwood 0.1.1) does with a string
`enum` on an OUTPUT field of an MCP tool, verified before any arm is built on it.

(a) the enum becomes an enumerated entity type in the generated schema, named <tool>_Output_<field>;
(b) validate rejects a non-member id (and a plain string literal, which is a type error) and accepts a member;
(c) description and default text never appear in the generated schema.
Plus two replay facts the arms depend on (no assertion about any generator):
(d) a plain-string trace value does NOT match an entity-typed predicate: a silent DENY, not an error, so a typed schema
    needs a typed trace suite (docs/decisions.md 2026-11-18);
(e) an optional enum output field that is absent from a recorded response simply does not match (no error).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pgi.oracle import temporal
from pgi.schemagen import generate_dogwood, link_session_id

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
T01 = DOMAIN / "scenarios" / "t01_close_after_approval"
EVENTS = DOMAIN / "schema" / "agentcore.dwschema"
AUTH = T01 / "manifests" / "authority.tools.json"
WO = T01 / "manifests" / "wo.maintenance-data.tools.json"
DECISIONS, KINDS = ["GRANTED", "REJECTED", "PENDING"], ["HUMAN", "AGENT", "SYSTEM"]
DEC_T, KIND_T = "Drupe::authority_get_approval_Output_decision", "Drupe::authority_get_approval_Output_approver_kind"


def _typed_authority(tmp_path: Path, extra: dict | None = None) -> Path:
    m = json.loads(AUTH.read_text())
    props = m["tools"][0]["outputSchema"]["properties"]
    props["decision"]["enum"], props["approver_kind"]["enum"] = DECISIONS, KINDS
    for k, v in (extra or {}).items():
        props[k].update(v)
    p = tmp_path / "authority.typed.json"
    p.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
    return p


@pytest.fixture(scope="module")
def typed(tmp_path_factory):
    """Schema = link_session_id(generate([wo, typed authority])), with description/default markers on approver_id."""
    d = tmp_path_factory.mktemp("typed")
    auth = _typed_authority(d, {"approver_id": {"description": "ZZDESCRIPTIONMARKER", "default": "ZZDEFAULTMARKER"}})
    gen = d / "generated.cedarschema"
    gen.write_text(generate_dogwood([WO, auth]))
    schema = d / "linked.cedarschema"
    schema.write_text(link_session_id(gen))
    return {"dir": d, "generated": gen.read_text(), "schema": schema}


def test_a_output_enum_becomes_an_enumerated_entity_type(typed):
    g = typed["generated"]
    assert f'entity authority_get_approval_Output_decision enum ["GRANTED", "REJECTED", "PENDING"];' in g
    assert f'entity authority_get_approval_Output_approver_kind enum ["HUMAN", "AGENT", "SYSTEM"];' in g
    assert f"decision: {DEC_T}" in g and f"approver_kind: {KIND_T}" in g
    base = (T01 / "schema" / "t01.dogwood.generated.cedarschema").read_text()
    assert "decision: String" in base and "decision: String" not in g  # the only typing change is on these two fields


def _gold_with(decision: str, kind: str) -> str:
    return (T01 / "gold.dw").read_text().replace('output.decision: "GRANTED"', f"output.decision: {decision}") \
        .replace('output.approver_kind: "HUMAN"', f"output.approver_kind: {kind}")


@pytest.mark.parametrize("decision,kind,ok,needle", [
    (f'{DEC_T}::"GRANTED"', f'{KIND_T}::"HUMAN"', True, None),
    (f'{DEC_T}::"APPROVED"', f'{KIND_T}::"HUMAN"', False, "not one of its permitted ids"),
    (f'{DEC_T}::"GRANTED"', f'{KIND_T}::"human"', False, "not one of its permitted ids"),
    ('"GRANTED"', '"HUMAN"', False, "expects `authority_get_approval_Output_decision` but got `string`"),
])
def test_b_validate_accepts_members_and_rejects_non_members_and_plain_strings(typed, tmp_path, decision, kind, ok, needle):
    p = tmp_path / "p.dw"
    p.write_text(_gold_with(decision, kind))
    r = temporal.check(p, typed["schema"], EVENTS)
    assert r.ok is ok, (r.errors, r.warnings)
    if needle:
        assert any(needle in e for e in r.errors), r.errors


def test_c_description_and_default_text_do_not_reach_the_schema(typed):
    assert "ZZDESCRIPTIONMARKER" not in typed["generated"] and "ZZDEFAULTMARKER" not in typed["generated"]
    assert "ZZDESCRIPTIONMARKER" not in typed["schema"].read_text()
    # and the manifest text that carried them is what the generator read
    assert "ZZDESCRIPTIONMARKER" in (typed["dir"] / "authority.typed.json").read_text()


def _typed_trace(text: str) -> str:
    out = []
    for line in text.splitlines():
        if '"authority_get_approval"::response(' in line:
            for k, v in (("decision", DECISIONS), ("approver_kind", KINDS)):
                for member in v:
                    line = line.replace(f'{k}: "{member}"', f'{k}: Drupe::authority_get_approval_Output_{k}::"{member}"')
        out.append(line)
    return "\n".join(out) + "\n"


def test_d_plain_string_trace_values_silently_fail_to_match_an_entity_typed_predicate(typed, tmp_path):
    gold = tmp_path / "typed_gold.dw"
    gold.write_text(_gold_with(f'{DEC_T}::"GRANTED"', f'{KIND_T}::"HUMAN"'))
    plain = T01 / "traces" / "t01_valid.log"
    assert temporal.decision(gold, typed["schema"], plain, EVENTS) is False      # silent deny, no OracleError
    typed_t01 = tmp_path / "t01_typed.log"
    typed_t01.write_text(_typed_trace(plain.read_text()))
    assert typed_t01.read_text() != plain.read_text()
    assert temporal.decision(gold, typed["schema"], typed_t01, EVENTS) is True
    # and the converse: a typed trace under the untyped schema/gold is also a silent deny
    assert temporal.decision(T01 / "gold.dw", T01 / "schema" / "t01.dogwood.cedarschema", typed_t01, EVENTS) is False


def test_e_absent_optional_enum_output_does_not_match_and_does_not_error(tmp_path):
    """A vendor output gains an optional enum field; a predicate on it does not match a response lacking the field."""
    wo = json.loads(WO.read_text())
    tool = next(t for t in wo["tools"] if t["name"] == "get_workorder")
    tool["outputSchema"]["properties"]["approval_outcome"] = {"enum": DECISIONS, "title": "Approval Outcome", "type": "string"}
    assert "approval_outcome" not in tool["outputSchema"]["required"]
    m = tmp_path / "wo.json"
    m.write_text(json.dumps(wo, indent=2, sort_keys=True) + "\n")
    gen = tmp_path / "g.cedarschema"
    gen.write_text(generate_dogwood([m, AUTH]))
    assert "approval_outcome?: Drupe::get_workorder_Output_approval_outcome" in gen.read_text()
    schema = tmp_path / "s.cedarschema"
    schema.write_text(link_session_id(gen))
    p = tmp_path / "vb.dw"
    p.write_text((T01 / "weak_vendorflag.dw").read_text().replace(
        'output.vendor_approval_status: "approved"', 'output.approval_outcome: Drupe::get_workorder_Output_approval_outcome::"GRANTED"'))
    assert temporal.check(p, schema, EVENTS).ok
    t08 = T01 / "traces" / "t08_vendor_flag_only.log"
    assert temporal.decision(p, schema, t08, EVENTS) is False                     # field absent: no match, no error
    present = tmp_path / "t15.log"
    present.write_text(t08.read_text().replace(
        'vendor_approval_status: "approved" }', 'vendor_approval_status: "approved", approval_outcome: Drupe::get_workorder_Output_approval_outcome::"GRANTED" }'))
    assert present.read_text() != t08.read_text()
    assert temporal.decision(p, schema, present, EVENTS) is True
