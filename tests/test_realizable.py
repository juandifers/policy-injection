"""Realizability of symcc counterexamples under cedar-policy-mcp-schema-generator 0.7.0's request encoding."""

from pathlib import Path

import pytest

from pgi.oracle import realizable, sym

ROOT = Path(__file__).resolve().parents[1]
WO = ROOT / "domains/assetopsbench/schema/wo.cedarschema"
TOY = ROOT / "domains/toy/schema/toy.cedarschema"

HEAD = 'principal: AOB::User::"", action: AOB::Action::"{action}", resource: AOB::McpServer::""'


def cex(action: str, context: str, entities: str = 'AOB::User::"", AOB::McpServer::""') -> str:
    return ("✗ Policy set 1 implies policy set 2: DOES NOT HOLD\n  Counterexample found:\n"
            f"{HEAD.format(action=action)}\ncontext: {context}\nentities: [\n  {entities},\n]")


def rules(text: str, schema: Path = WO) -> set[str]:
    return {v.rule for v in realizable.check(sym.parse_counterexample(text), schema).violations}


@pytest.fixture(autouse=True, scope="module")
def _cedar(request):
    try:
        sym.check_available()
    except sym.SymccUnavailable as e:
        pytest.skip(str(e))


def test_plain_strings_are_realizable():
    assert rules(cex("close_workorder", '{input: {site_id: "MAIN", wonum: "1000046"}}')) == set()


def test_r1_union_with_no_branch_is_unrealizable():
    # The shape symcc actually returned for weak_same_wo in Step 2.
    text = cex("close_workorder", '{approval: {approver: AOB::User::"A", status: "APPR", wonum: ""}, '
                                  'input: {resolution_notes: {}, site_id: "MAIN", wonum: "MAIN"}}')
    report = realizable.check(sym.parse_counterexample(text), WO)
    assert not report.realizable
    assert [(v.rule, v.path) for v in report.violations] == [("R1", "context.input.resolution_notes")]


def test_r1_union_with_both_branches_is_unrealizable():
    ctx = '{input: {failure_code: {typeChoice0: "X", typeChoice1: AOB::Null::"null"}, site_id: "MAIN", wonum: "1"}}'
    assert rules(cex("close_workorder", ctx)) == {"R1"}


def test_r1_union_with_one_branch_is_realizable():
    ctx = '{input: {failure_code: {typeChoice1: AOB::Null::"null"}, site_id: "MAIN", wonum: "1"}}'
    assert rules(cex("close_workorder", ctx)) == set()


def test_r2_null_must_have_id_null():
    ctx = '{input: {failure_code: {typeChoice1: AOB::Null::""}, site_id: "MAIN", wonum: "1"}}'
    assert rules(cex("close_workorder", ctx)) == {"R2"}


@pytest.mark.parametrize("eid,ok", [("2.5", True), ("-1", True), ("1e3", True), ("0", True), ("", False), ("A", False), ("01", False)])
def test_r3_number_must_be_a_json_number_literal(eid, ok):
    ctx = f'{{input: {{actual_hours: AOB::Number::"{eid}", site_id: "MAIN", wonum: "1"}}}}'
    assert rules(cex("close_workorder", ctx)) == (set() if ok else {"R3"})


@pytest.mark.parametrize("eid,ok", [("3f2b8c1e-9d4a-4c6b-8a2e-1f0d9c8b7a6e", True), ("", False), ("not-a-uuid", False)])
def test_r5_object_entity_must_have_a_v4_uuid(eid, ok):
    ctx = ('{input: {asset_num: "PUMP3", description: "x", site_id: "MAIN", '
           f'aob_source: {{typeChoice0: AOB::generate_work_order::Input::aob_source::TypeChoice0::"{eid}"}}}}}}')
    assert rules(cex("generate_work_order", ctx)) == (set() if ok else {"R5"})


def test_r7_trusted_context_is_assumed_realizable_and_r8_any_entity_id():
    ctx = '{approval: {approver: AOB::User::"", status: "", wonum: ""}, input: {site_id: "MAIN", wonum: "1"}}'
    assert rules(cex("close_workorder", ctx)) == set()


def test_toy_schema_has_no_generator_encoding_so_everything_is_realizable():
    ctx = '{approval: {approver: AOB::User::"A", status: "APPR", wonum: ""}, input: {siteid: "MAIN", wonum: "MAIN"}}'
    assert rules(cex("close_work_order", ctx), TOY) == set()


def test_classify_verified_realizable_undetermined():
    assert realizable.classify(sym.VERIFIED, WO).status == "holds"
    good = cex("close_workorder", '{input: {site_id: "MAIN", wonum: "1"}}')
    bad = cex("close_workorder", '{input: {resolution_notes: {}, site_id: "MAIN", wonum: "1"}}')
    assert realizable.classify(good, WO).status == "does_not_hold"
    assert realizable.classify(bad, WO).status == "undetermined"
