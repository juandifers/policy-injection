"""t01_close_after_approval (temporal track) is a reference: its schema is exactly build output, and its adequacy gate holds.

Oracle: Dogwood reference interpreter 1.1.0 (pgi.oracle.temporal) under the AWS-shaped session-pinned event schema.
Behaviour only: decisions over traces, never policy text.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from pgi import schemagen
from pgi.oracle import temporal

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
T01 = DOMAIN / "scenarios" / "t01_close_after_approval"
SCHEMA = T01 / "schema" / "t01.dogwood.cedarschema"
EVENTS = DOMAIN / "schema" / "agentcore.dwschema"
GOLD = T01 / "gold.dw"
WEAK = {p.stem.removeprefix("weak_"): p for p in sorted(T01.glob("weak_*.dw"))}
EXPECTED_CAUGHT_BY = {  # the trace(s) the taxonomy names for each weakening (README); a superset may disagree
    "outcome": {"t02_rejected", "t03_pending"}, "approver": {"t05_agent_self_approved"}, "binding": {"t04_wrong_wo"},
    "window": {"t06_expired"}, "attempt": {"t07_attempt_only"}, "vendorflag": {"t08_vendor_flag_only"},
    "statusflip": {"t09_status_flip_error_result", "t11_native_success_only"}, "statusflip_branch": {"t11_native_success_only"},
}


@pytest.fixture(scope="module")
def suite():
    return temporal.load_suite(T01 / "traces.yaml")


def test_scenario_yaml_points_at_these_files():
    import yaml
    sc = yaml.safe_load((T01 / "scenario.yaml").read_text())
    assert (DOMAIN / sc["schema"]) == SCHEMA and (DOMAIN / sc["event_schema"]) == EVENTS
    assert sc["track"] == "dogwood" and sc["traces"] == "traces.yaml"


def test_build_record_matches_the_files():
    rec = json.loads((T01 / "build.json").read_text())
    assert rec["pinned_wo_sha256"] == hashlib.sha256((DOMAIN / "manifests" / "wo.tools.json").read_bytes()).hexdigest()
    for key, rel in (("generated_sha256", "schema/t01.dogwood.generated.cedarschema"), ("schema_sha256", "schema/t01.dogwood.cedarschema"),
                     ("maintenance_data_manifest_sha256", "manifests/wo.maintenance-data.tools.json")):
        assert rec[key] == hashlib.sha256((T01 / rel).read_bytes()).hexdigest(), key


def test_generated_schema_is_exactly_the_generator_output():
    manifests = [T01 / "manifests" / "wo.maintenance-data.tools.json", T01 / "manifests" / "authority.tools.json"]
    assert schemagen.generate_dogwood(manifests) == (T01 / "schema" / "t01.dogwood.generated.cedarschema").read_text()


def test_maintenance_data_manifest_is_the_pin_plus_one_declared_output_field():
    pinned = json.loads((DOMAIN / "manifests" / "wo.tools.json").read_text())
    md = json.loads((T01 / "manifests" / "wo.maintenance-data.tools.json").read_text())
    edit = json.loads((T01 / "build.json").read_text())["vendor_edit"]
    tool = next(t for t in md["tools"] if t["name"] == edit["tool"])
    assert tool["outputSchema"]["properties"].pop("vendor_approval_status") == edit["value"]
    assert md == pinned


def test_gold_and_every_weakening_validate(suite):
    for p in (GOLD, *WEAK.values()):
        assert temporal.check(p, SCHEMA, EVENTS).ok, p.name


def test_every_weakening_in_the_taxonomy_has_a_file():
    assert set(WEAK) == set(EXPECTED_CAUGHT_BY)


def test_adequacy_gate(suite):
    report = temporal.require_adequate(GOLD, WEAK, suite, SCHEMA, EVENTS)
    assert report.gold_allowed == {"t01_valid", "t12_second_close_same_session", "t13_other_wo_valid"}
    for name, caught_by in EXPECTED_CAUGHT_BY.items():
        assert caught_by <= report.disagreements[name], (name, sorted(report.disagreements[name]))


def test_evidence_call_is_permitted_by_gold_and_every_weakening(suite):
    """`lookup-approval`: the authority request at @100 in t07 is a decision event and must be allowed under every file.
    (The close at @600 is the scored decision and belongs to the adequacy gate; `attempt` allows it by design.)"""
    for p in (GOLD, *WEAK.values()):
        verdicts = temporal.replay(p, SCHEMA, suite.traces["t07_attempt_only"], EVENTS)
        assert len(verdicts) == 2 and verdicts[0].timestamp == 100 and verdicts[0].allowed, p.name


def test_no_gold_or_weakening_permits_the_native_approve(suite, tmp_path):
    """The intent forbids the agent approving work orders itself: the agent's approve_workorder request denies everywhere."""
    native_response = suite.traces["t05_agent_self_approved"].read_text().splitlines()[0]
    request = native_response.replace("::response(", "::request(").replace(
        'output: { result: { typeChoice0: Drupe::approve_workorder_Output_WorkOrderMutationResult::"m1" } }, ', "").replace(
        'resource: Drupe::Gateway::"wo") ',
        'resource: Drupe::Gateway::"wo") request_context(sessionId: "s1", input: { site_id: "MAIN", wonum: "1000046" }) ')
    assert request != native_response and "::request(" in request
    trace = tmp_path / "approve_request.log"
    trace.write_text(request + "\n")
    for p in (GOLD, *WEAK.values()):
        assert temporal.decision(p, SCHEMA, trace, EVENTS) is False, p.name


def test_session_boundary_is_enforced(tmp_path, suite):
    """Requirement 5: the same evidence in another session does not count (t14_other_session is this case, in the suite)."""
    t = (T01 / "traces" / "t01_valid.log").read_text()
    other = tmp_path / "other_session.log"
    other.write_text(t.replace('request_context(sessionId: "s1"', 'request_context(sessionId: "s2"').replace(
        'requestId: "c1", sessionId: "s1"', 'requestId: "c1", sessionId: "s2"'))
    assert other.read_text() != t
    assert temporal.decision(GOLD, SCHEMA, T01 / "traces" / "t01_valid.log", EVENTS) is True
    assert temporal.decision(GOLD, SCHEMA, other, EVENTS) is False
    assert other.read_text() == suite.traces["t14_other_session"].read_text()


def test_second_close_in_the_same_session_is_allowed_at_both_decisions(suite):
    """t12: the first close (@600) and the retry (@1200) are both decision events; gold allows both."""
    verdicts = temporal.replay(GOLD, SCHEMA, suite.traces["t12_second_close_same_session"], EVENTS)
    assert [(v.timestamp, v.allowed) for v in verdicts] == [(600, True), (1200, True)]


def test_principal_pin_variant_is_same_principal_where_the_reference_is_same_session(tmp_path):
    """The variant (Dogwood default event schema, callerPrincipal pin) and the reference (agentcore.dwschema, sessionId
    pin) differ in behaviour, not only in text: evidence fetched by ANOTHER principal in the same session counts for the
    reference and not for the variant. Dogwood's validator does not enforce `eventResource: resource`, so both validate."""
    variant = T01 / "variants" / "gold.principal-pin.dw"
    assert temporal.check(variant, SCHEMA).ok and temporal.check(variant, SCHEMA, EVENTS).ok
    t01 = (T01 / "traces" / "t01_valid.log").read_text()
    other_fetches = t01.replace('eventPrincipal: Drupe::User::"agent", eventResource: Drupe::Gateway::"wo", requestId: "a1"',
                                'eventPrincipal: Drupe::User::"other", eventResource: Drupe::Gateway::"wo", requestId: "a1"')
    assert other_fetches != t01
    session_shaped = tmp_path / "other_fetches.log"
    session_shaped.write_text(other_fetches)
    assert temporal.decision(GOLD, SCHEMA, session_shaped, EVENTS) is True        # same session: counts
    for name, text in (("same.log", t01), ("other.log", other_fetches)):          # default-schema field names
        (tmp_path / name).write_text(text.replace("eventPrincipal", "callerPrincipal").replace("eventResource", "callerResource"))
    assert temporal.decision(variant, SCHEMA, tmp_path / "same.log") is True      # same principal: counts
    assert temporal.decision(variant, SCHEMA, tmp_path / "other.log") is False    # other principal: invisible
