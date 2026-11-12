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


# ---- R1/R2 exclusion built into the symbolic backend -------------------------------------------------

DOMAINS = ROOT / "domains"
UNIVERSES = [  # (universe, schema) for every scenario in every domain
    (DOMAINS / "toy/scenarios/s01_close_after_approval/universe.yaml", TOY),
    (DOMAINS / "assetopsbench/scenarios/s01_close_after_approval/universe.yaml", WO),
    (DOMAINS / "assetopsbench/scenarios/s02_site_scoped_reads/universe.yaml", ROOT / "domains/assetopsbench/schema/wo_iot.cedarschema"),
    (DOMAINS / "assetopsbench/scenarios/s03_create_at_main/universe.yaml", WO),
]


def test_every_universe_is_listed():
    found = {p for p in DOMAINS.glob("*/scenarios/*/universe.yaml")}
    assert found == {u for u, _ in UNIVERSES}, "a new scenario must be added to UNIVERSES"


@pytest.mark.parametrize("universe_path,schema", UNIVERSES, ids=lambda x: x.parent.name if x.name == "universe.yaml" else x.name)
def test_exclusion_never_blocks_a_realistic_request(universe_path, schema, tmp_path):
    """Allow-everything plus the exclusion must still allow every request in the universe."""
    from pgi.oracle.enumeration import allowed, load_universe
    from pgi.oracle.validation import check
    guarded = tmp_path / "allow_all_guarded.cedar"
    guarded.write_text("permit (principal, action, resource);\n" + realizable.exclusion_policy(schema))
    assert check(guarded, schema).ok, check(guarded, schema)
    universe = load_universe(universe_path)
    assert allowed(guarded, universe, schema) == set(universe.ids)


def test_exclusion_blocks_the_unrealizable_shapes(tmp_path):
    """The exclusion must actually forbid R1 and R2 violations, not just pass everything."""
    from pgi.oracle.enumeration import Universe, allowed
    guarded = tmp_path / "g.cedar"
    guarded.write_text("permit (principal, action, resource);\n" + realizable.exclusion_policy(WO))
    act = {"type": "AOB::Action", "id": "close_workorder"}
    base = {"site_id": "MAIN", "wonum": "1"}
    null = lambda i: {"__entity": {"type": "AOB::Null", "id": i}}
    cases = {
        "ok_one_branch": {**base, "failure_code": {"typeChoice0": "X"}},
        "ok_null": {**base, "failure_code": {"typeChoice1": null("null")}},
        "r1_none": {**base, "resolution_notes": {}},
        "r1_both": {**base, "failure_code": {"typeChoice0": "X", "typeChoice1": null("null")}},
        "r2_bad_null": {**base, "failure_code": {"typeChoice1": null("")}},
    }
    u = Universe({k: {"principal": {"type": "AOB::User", "id": "a"}, "action": act,
                      "resource": {"type": "AOB::McpServer", "id": "wo"}, "context": {"input": v}} for k, v in cases.items()}, [], {})
    assert allowed(guarded, u, WO) == {"ok_one_branch", "ok_null"}


def test_toy_schema_needs_no_exclusion():
    assert realizable.exclusion_policy(TOY) == ""


@pytest.mark.parametrize("name", ["weak_status", "weak_same_wo", "weak_self"])
def test_realizable_implies_finds_the_real_surplus(name):
    """With the exclusion, symcc's counterexample on close is realizable and replays in cedarpy."""
    from pgi.oracle.enumeration import Universe, allowed
    folder = DOMAINS / "assetopsbench/scenarios/s01_close_after_approval"
    results = realizable.implies(folder / f"{name}.cedar", folder / "reference.cedar", WO)
    close = {e: c for e, c in results.items() if e.action == 'AOB::Action::"close_workorder"'}
    others = {e: c for e, c in results.items() if e not in close}
    (c,) = close.values()
    assert c.status == "does_not_hold" and c.violations == ()
    one = Universe({"cex": c.counterexample["request"]}, c.counterexample["entities"], {})
    assert allowed(folder / f"{name}.cedar", one, WO) == {"cex"}    # replayed against the ORIGINAL P1
    assert allowed(folder / "reference.cedar", one, WO) == set()
    assert all(o.status == "holds" for o in others.values())


def test_realizable_implies_reference_holds_everywhere():
    folder = DOMAINS / "assetopsbench/scenarios/s01_close_after_approval"
    results = realizable.implies(folder / "reference.cedar", folder / "reference.cedar", WO)
    assert len(results) == 15 and all(c.status == "holds" for c in results.values())
