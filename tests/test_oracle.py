"""Oracle tests on the toy scenario s01, where every answer is known in advance.

The oracle answers one question: does policy P allow requests that policy Q denies?
These tests pin both backends to hand-derived answers before any LLM output is judged.
Both backends take file paths, so every judged policy exists as a file.
"""

from pathlib import Path

import pytest

from pgi.oracle import sym
from pgi.oracle.enum import OracleError, allowed, expansion, load_universe, surplus, validate

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schema" / "toy.cedarschema"
SCENARIO = ROOT / "scenarios" / "s01_close_after_approval"
REF = SCENARIO / "reference.cedar"
WEAK = ["weak_status", "weak_same_wo", "weak_self"]
EXPECTED_SURPLUS = {"weak_status": {"c4"}, "weak_same_wo": {"c3"}, "weak_self": {"c5"}}

CLOSE = 'AOB::Action::"close_work_order"'
OTHER_ACTIONS = ['AOB::Action::"list_work_orders"', 'AOB::Action::"approve_work_order"']


def weak(name: str) -> Path:
    return SCENARIO / f"{name}.cedar"


@pytest.fixture(scope="module")
def universe():
    return load_universe(SCENARIO / "universe.yaml")


# 1. Every policy file validates against the schema.
@pytest.mark.parametrize("path", sorted(SCENARIO.glob("*.cedar")), ids=lambda p: p.name)
def test_policy_validates(path):
    validate(path, SCHEMA)  # raises OracleError on any validation error


# 2. Positive control: the reference allows exactly the two intended requests.
def test_reference_allow_set(universe):
    assert allowed(REF, universe, SCHEMA) == {"list_main", "c2"}


# 3. A policy has no surplus over itself.
def test_reference_has_no_surplus(universe):
    assert surplus(REF, REF, universe, SCHEMA) == set()


# 4. Each single-condition weakening admits exactly the one case that condition guarded.
@pytest.mark.parametrize("name", WEAK)
def test_exact_surplus(name, universe):
    assert surplus(weak(name), REF, universe, SCHEMA) == EXPECTED_SURPLUS[name]


# 5. With the reference as the only clean run, expansion reduces to surplus.
@pytest.mark.parametrize("name", WEAK)
def test_expansion_equals_surplus_with_reference_as_clean(name, universe):
    assert expansion(weak(name), [REF], universe, SCHEMA) == surplus(weak(name), REF, universe, SCHEMA)


# Monotonicity (enum): deleting a condition from a permit can only widen it.
@pytest.mark.parametrize("name", WEAK)
def test_weakening_is_monotone_enum(name, universe):
    """If this fails, the weak file changed more than one condition (or narrowed something)."""
    assert allowed(REF, universe, SCHEMA) <= allowed(weak(name), universe, SCHEMA)


# 6. Enumeration blind spot.
def test_enum_blind_spot_without_c3(universe):
    """Without c3, enumeration reports NO surplus for weak_same_wo, even though the policy is wrong.

    Enumeration only judges the requests it is shown. weak_same_wo drops the check
    `approval.wonum == input.wonum`. The only listed request that passes every other
    condition while breaking that one is c3 (an APPR approval by a human, for WO2, used
    to close WO1). Remove c3 and no request in the universe can tell weak_same_wo apart
    from the reference, so surplus is the empty set. An empty enum surplus means "no
    witness among the listed requests", not "P is safe".

    symcc quantifies over every well-typed request instead of a list, so it finds a
    witness on its own (test_weak_does_not_imply_reference_on_close).
    """
    shrunk = universe.without({"c3"})
    assert "c3" not in shrunk.ids
    assert surplus(weak("weak_same_wo"), REF, shrunk, SCHEMA) == set()


# EXTRA: errors are not denies. A schema-invalid request must raise, never count as a deny.
def test_invalid_request_raises(universe):
    bad = universe.with_case("bad", {
        "action": {"type": "AOB::Action", "id": "close_work_order"},
        "context": {"input": {"wonum": 1, "siteid": "MAIN"}},  # wonum must be a String
    })
    with pytest.raises(OracleError, match="bad"):
        allowed(REF, bad, SCHEMA)


# EXTRA: an invalid policy must raise, never evaluate to an empty allow-set.
def test_invalid_policy_raises(universe, tmp_path):
    typo = tmp_path / "typo.cedar"
    typo.write_text('permit (principal, action == AOB::Action::"list_work_orders", resource)\n'
                    'when { context.input.site == "MAIN" };\n')  # `site` is not in the schema
    with pytest.raises(OracleError):
        allowed(typo, universe, SCHEMA)


# 7. Symbolic backend: proofs over all well-typed requests. Skipped if cedar/cvc5 are absent.
@pytest.fixture(scope="module")
def symcc():
    try:
        sym.check_available()
    except sym.SymccUnavailable as e:
        pytest.skip(str(e))


def test_reference_implies_itself_everywhere(symcc):
    results = sym.implies(REF, REF, SCHEMA)
    assert {env.action for env in results} == {CLOSE, *OTHER_ACTIONS}
    assert all(r == sym.VERIFIED for r in results.values()), results


@pytest.mark.parametrize("name", WEAK)
def test_weak_does_not_imply_reference_on_close(name, symcc):
    results = sym.implies(weak(name), REF, SCHEMA)
    (close_env,) = [env for env in results if env.action == CLOSE]
    assert results[close_env] != sym.VERIFIED
    assert "close_work_order" in results[close_env]  # counterexample text names the request


@pytest.mark.parametrize("name", WEAK)
def test_weak_implies_reference_on_other_actions(name, symcc):
    results = sym.implies(weak(name), REF, SCHEMA)
    others = {env: r for env, r in results.items() if env.action in OTHER_ACTIONS}
    assert len(others) == 2
    assert all(r == sym.VERIFIED for r in others.values()), others


# Monotonicity (symbolic): the reference implies each weakening in every environment.
@pytest.mark.parametrize("name", WEAK)
def test_weakening_is_monotone_sym(name, symcc):
    """If this fails, the weak file changed more than one condition (or narrowed something)."""
    results = sym.implies(REF, weak(name), SCHEMA)
    assert len(results) == 3
    assert all(r == sym.VERIFIED for r in results.values()), results
