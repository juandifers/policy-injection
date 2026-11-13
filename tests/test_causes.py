"""Cause tags: which conjunct of a policy denies a given request. Deterministic (cedarpy + Cedar CLI), no LLM.

Surplus case -> explain with the reference (which conjunct of P_ref denies it).
Deficit case -> explain with the candidate (which conjunct of P denies it).
"""

import json
import shutil
from pathlib import Path

import pytest

from pgi.oracle.causes import causes, explain
from pgi.oracle.enumeration import load_universe
from pgi.runs.snapshot import load_snapshot

ROOT = Path(__file__).resolve().parents[1]
TOY = ROOT / "domains" / "toy"
TS01 = TOY / "scenarios" / "s01_close_after_approval"
TSCHEMA = TOY / "schema" / "toy.cedarschema"
SMOKE1 = ROOT / "runs" / "20261112T194818Z-clean-smoke"
SMOKE1_INPUTS = ROOT / "tests" / "fixtures" / "smoke1_inputs"

STATUS = 'context.approval.status == "APPR"'
WONUM = "context.approval.wonum == context.input.wonum"
# Tags use the Cedar CLI's canonical printing (JSON -> Cedar): `a != b` prints as `!(a == b)`, and
# `||` operands are parenthesised. Canonical text lets the same condition, written two ways, share one tag.
APPROVER = "!(context.approval.approver == principal)"
HAS = "context has approval"
CLOSE_HEAD = 'permit (principal, action == AOB::Action::"close_work_order", resource)'


@pytest.fixture(autouse=True)
def _cedar():
    if shutil.which("cedar") is None:
        pytest.skip("cedar CLI not on PATH")


@pytest.fixture(scope="module")
def universe():
    return load_universe(TS01 / "universe.yaml")


def write(tmp_path, text, name="p.cedar"):
    (tmp_path / name).write_text(text)
    return tmp_path / name


def close_permit(pid, cond):
    return f'@id("{pid}")\n{CLOSE_HEAD}\nwhen {{ {cond} }};\n'


# ---- surplus cases of the toy weak files, explained by the reference
@pytest.mark.parametrize("case,conjunct", [("c4", STATUS), ("c3", WONUM), ("c5", APPROVER)])
def test_reference_conjunct_that_denies_each_weak_files_surplus(case, conjunct, universe):
    e = explain(TS01 / "reference.cedar", case, universe, TSCHEMA)
    (p,) = e["permits"]
    assert p["id"] == "close-after-approval" and not p["allows"]
    assert p["first_blocker"] == conjunct
    assert p["sole_blockers"] == [conjunct]
    assert e["tag"] == [f"close-after-approval: {conjunct}"]


def test_causes_routes_surplus_to_reference_and_deficit_to_candidate(tmp_path, universe):
    weak = TS01 / "weak_status.cedar"
    c = causes(weak, TS01 / "reference.cedar", ["c4"], [], universe, TSCHEMA)
    assert list(c["surplus"]) == ["c4"] and c["deficit"] == {}
    assert c["surplus"]["c4"]["tag"] == [f"close-after-approval: {STATUS}"]


# ---- leave-one-out vs prefix scan
def test_prefix_and_leave_one_out_differ_when_two_conjuncts_block(tmp_path, universe):
    """c6 is at the wrong site AND (here) self-approved: the prefix scan names the first, no single removal flips."""
    req = load_universe(TS01 / "universe.yaml")
    u = req.with_case("c6x", {**req.requests["c6"], "context": {**req.requests["c6"]["context"],
                       "approval": {**req.requests["c6"]["context"]["approval"],
                                    "approver": {"__entity": {"type": "AOB::User", "id": "agent"}}}}})
    e = explain(TS01 / "reference.cedar", "c6x", u, TSCHEMA)
    (p,) = e["permits"]
    assert p["first_blocker"] == 'context.input.siteid == "MAIN"'
    assert p["sole_blockers"] == []


def test_removal_that_errors_is_no_flip_and_is_recorded(universe):
    """c1 has no approval: the `has` guard blocks; removing it makes the next conjunct error (not a flip)."""
    e = explain(TS01 / "reference.cedar", "c1", universe, TSCHEMA)
    (p,) = e["permits"]
    assert p["first_blocker"] == HAS
    assert p["sole_blockers"] == []
    assert p["loo_errors"] == [HAS]


# ---- deficit: candidate stricter than the reference
def test_deficit_where_candidate_is_stricter(tmp_path, universe):
    strict = write(tmp_path, close_permit("strict", f'{HAS} && {STATUS} && context.input.wonum == "WO9"'))
    c = causes(strict, TS01 / "reference.cedar", [], ["c2"], universe, TSCHEMA)
    assert c["deficit"]["c2"]["tag"] == ['strict: context.input.wonum == "WO9"']
    assert c["deficit"]["c2"]["permits"][0]["sole_blockers"] == ['context.input.wonum == "WO9"']


def test_nested_and_is_flattened_on_both_sides(tmp_path, universe):
    nested = write(tmp_path, close_permit("nested", f'({HAS} && {STATUS}) && ({WONUM} && context.input.wonum == "WO9")'))
    (p,) = explain(nested, "c2", universe, TSCHEMA)["permits"]
    assert p["conjuncts"] == [HAS, STATUS, WONUM, 'context.input.wonum == "WO9"']
    assert p["first_blocker"] == 'context.input.wonum == "WO9"' and p["first_blocker_index"] == 4


def test_or_inside_a_conjunct_is_one_conjunct(tmp_path, universe):
    pol = write(tmp_path, close_permit("or", f'{HAS} && (context.input.wonum == "WO8" || context.input.wonum == "WO9")'))
    (p,) = explain(pol, "c2", universe, TSCHEMA)["permits"]
    assert p["conjuncts"] == [HAS, '(context.input.wonum == "WO8") || (context.input.wonum == "WO9")']
    assert p["first_blocker"] == p["conjuncts"][1]


def test_unless_is_one_negated_conjunct_and_when_clauses_are_joined(tmp_path, universe):
    pol = write(tmp_path, f'@id("u")\n{CLOSE_HEAD}\nwhen {{ {HAS} }}\nwhen {{ {STATUS} }}\nunless {{ {WONUM} }};\n')
    (p,) = explain(pol, "c2", universe, TSCHEMA)["permits"]
    assert p["conjuncts"] == [HAS, STATUS, f"!({WONUM})"]
    assert p["first_blocker"] == f"!({WONUM})"


def test_several_permits_get_one_tag_each(tmp_path, universe):
    two = write(tmp_path, close_permit("a", f'{HAS} && context.input.wonum == "WO8"')
                + close_permit("b", f'{HAS} && {STATUS} && context.input.siteid == "PLANT9"'))
    e = explain(two, "c2", universe, TSCHEMA)
    assert e["tag"] == ['a: context.input.wonum == "WO8"', 'b: context.input.siteid == "PLANT9"']


def test_forbid_that_fires_is_reported_before_permits(tmp_path, universe):
    pol = write(tmp_path, (TS01 / "reference.cedar").read_text()
                + '\n@id("no-main-close")\nforbid (principal, action == AOB::Action::"close_work_order", resource)\n'
                  'when { context.input.siteid == "MAIN" };\n')
    e = explain(pol, "c2", universe, TSCHEMA)
    assert e["tag"] == "forbid: no-main-close"
    assert e["forbids"] == [{"id": "no-main-close", "fired": True, "error": None}]


def test_action_not_granted(tmp_path, universe):
    only_close = write(tmp_path, close_permit("c", HAS))
    assert explain(only_close, "list_main", universe, TSCHEMA)["tag"] == "action not granted"


def test_probe_that_errors_is_unexplained_error(tmp_path, universe):
    """No `has` guard: on c1 (no approval) the first conjunct errors; Cedar skips the policy, we never call it a deny."""
    pol = write(tmp_path, close_permit("e", STATUS))
    e = explain(pol, "c1", universe, TSCHEMA)
    (p,) = e["permits"]
    assert p["first_blocker_error"] and e["tag"] == ["e: unexplained: error"]


# ---- the smoke-run example, on the inputs that run actually used (restored from git faf37e6)
def test_smoke1_deficit_c2_is_the_approved_status_conjunct():
    inp = load_snapshot(SMOKE1_INPUTS / "s01_close_after_approval")
    policy = SMOKE1 / "s01_close_after_approval" / "naive" / "sample_00" / "policy.cedar"
    oracle = json.loads((policy.parent / "oracle.json").read_text())
    c = causes(policy, inp.reference, oracle["enumeration"]["surplus"], oracle["enumeration"]["deficit"],
               load_universe(inp.universe), inp.schema_path)
    (p,) = c["deficit"]["c2"]["permits"]
    assert p["first_blocker"] == 'context.approval.status == "APPROVED"'
    assert p["sole_blockers"] == ['context.approval.status == "APPROVED"']
