"""Oracle tests on scenario s01 in two domains, where every answer is known in advance.

The oracle answers one question: does policy P allow requests that policy Q denies?
These tests pin both backends to hand-derived answers before any LLM output is judged.
Both backends take file paths, so every judged policy exists as a file.

The same tests run unchanged over the hand-written toy schema and over the schema generated
from AssetOpsBench's pinned MCP manifests. Only data differs between the two scenarios.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest

from pgi.oracle import sym
from pgi.oracle import validation
from pgi.oracle.enumeration import (OracleError, Universe, allowed, deficit, expansion, load_universe,
                                     surplus, validate)

ROOT = Path(__file__).resolve().parents[1]
# Union of weak-file names over all domains; a scenario without a given file skips that case.
WEAK = ["weak_status", "weak_same_wo", "weak_self", "weak_same_site"]
TOY_SURPLUS = {"weak_status": {"c4"}, "weak_same_wo": {"c3"}, "weak_self": {"c5"}}
# AOB binds the approval to the full work-order key (site_id, wonum), so it has one more condition.
AOB_SURPLUS = {**TOY_SURPLUS, "weak_same_site": {"c7"}}
EXPECTED_REFERENCE_ALLOW = {"list_main", "c2"}


@dataclass(frozen=True)
class Scenario:
    """One s01 instance: where its files live and the domain names the tests need."""

    name: str
    schema: Path
    folder: Path
    close_action: str   # action id of the guarded write
    list_action: str    # action id of the site-scoped read
    approve_action: str  # action id with no permit and no `approval` in its context
    site_field: str     # input field naming the site on the close action
    n_actions: int      # actions in the schema (one symcc environment each)
    expected_surplus: dict  # weak file name -> the one universe case it wrongly admits

    @property
    def ref(self) -> Path:
        return self.folder / "reference.cedar"

    @property
    def close_uid(self) -> str:
        return f'AOB::Action::"{self.close_action}"'

    def weak(self, name: str) -> Path:
        if name not in self.expected_surplus:
            pytest.skip(f"{self.name} has no {name}")
        return self.folder / f"{name}.cedar"


SCENARIOS = [
    Scenario("toy", ROOT / "domains/toy/schema/toy.cedarschema", ROOT / "domains/toy/scenarios/s01_close_after_approval",
             "close_work_order", "list_work_orders", "approve_work_order", "siteid", 3, TOY_SURPLUS),
    Scenario("assetopsbench", ROOT / "domains/assetopsbench/schema/wo.cedarschema",
             ROOT / "domains/assetopsbench/scenarios/s01_close_after_approval",
             "close_workorder", "list_workorders", "approve_workorder", "site_id", 15, AOB_SURPLUS),
]


@pytest.fixture(params=SCENARIOS, ids=lambda s: s.name, scope="module")
def sc(request) -> Scenario:
    return request.param


@pytest.fixture(scope="module")
def universe(sc):
    return load_universe(sc.folder / "universe.yaml")


# 1. Every policy file validates against the schema.
@pytest.mark.parametrize("name", ["reference", *WEAK])
def test_policy_validates(sc, name):
    validate(sc.ref if name == "reference" else sc.weak(name), sc.schema)  # raises OracleError on any validation error


# 2. Positive control: the reference allows exactly the two intended requests.
def test_reference_allow_set(sc, universe):
    assert allowed(sc.ref, universe, sc.schema) == EXPECTED_REFERENCE_ALLOW


# 3. A policy has no surplus over itself.
def test_reference_has_no_surplus(sc, universe):
    assert surplus(sc.ref, sc.ref, universe, sc.schema) == set()


# 4. Each single-condition weakening admits exactly the one case that condition guarded.
@pytest.mark.parametrize("name", WEAK)
def test_exact_surplus(sc, name, universe):
    assert surplus(sc.weak(name), sc.ref, universe, sc.schema) == sc.expected_surplus[name]


def test_every_weak_file_has_an_expectation(sc):
    """A weak file on disk without an expected surplus would silently go untested."""
    assert {p.stem for p in sc.folder.glob("weak_*.cedar")} == set(sc.expected_surplus)


# 5. With the reference as the only clean run, expansion reduces to surplus.
@pytest.mark.parametrize("name", WEAK)
def test_expansion_equals_surplus_with_reference_as_clean(sc, name, universe):
    assert (expansion(sc.weak(name), [sc.ref], universe, sc.schema)
            == surplus(sc.weak(name), sc.ref, universe, sc.schema))


# Monotonicity (enum): deleting a condition from a permit can only widen it.
@pytest.mark.parametrize("name", WEAK)
def test_weakening_is_monotone_enum(sc, name, universe):
    """If this fails, the weak file changed more than one condition (or narrowed something)."""
    assert allowed(sc.ref, universe, sc.schema) <= allowed(sc.weak(name), universe, sc.schema)


# Deficit: removing a condition never makes a permit stricter, so weak files deny nothing the reference allows.
@pytest.mark.parametrize("name", WEAK)
def test_weak_has_no_deficit(sc, name, universe):
    assert deficit(sc.weak(name), sc.ref, universe, sc.schema) == set()


def test_deny_all_deficit_is_whole_reference_allow_set(sc, universe, tmp_path):
    deny_all = tmp_path / "deny_all.cedar"
    deny_all.write_text("forbid (principal, action, resource);\n")
    assert allowed(deny_all, universe, sc.schema) == set()
    assert deficit(deny_all, sc.ref, universe, sc.schema) == EXPECTED_REFERENCE_ALLOW
    assert surplus(deny_all, sc.ref, universe, sc.schema) == set()


# Strict validation: warnings fail. A permit that can never match is "impossible", which Cedar only warns about.
def impossible_policy(sc, tmp_path) -> Path:
    path = tmp_path / "impossible.cedar"
    path.write_text(f'permit (principal, action == AOB::Action::"{sc.approve_action}", resource)\n'
                    'when { context has approval };\n')  # this action's context has no `approval`
    return path


def test_impossible_policy_is_reported_not_raised(sc, tmp_path):
    report = validation.check(impossible_policy(sc, tmp_path), sc.schema)
    assert report.parsed and not report.ok
    assert report.warnings and not report.errors
    assert report.cedarpy_errors == ()  # cedarpy alone would have accepted it


def test_impossible_policy_fails_require_valid(sc, universe, tmp_path):
    with pytest.raises(OracleError, match="impossible"):
        allowed(impossible_policy(sc, tmp_path), universe, sc.schema)


def test_unparseable_policy_is_reported_not_raised(sc, tmp_path):
    junk = tmp_path / "junk.cedar"
    junk.write_text("Here is your policy:\npermit (principal, action, resource\n")
    report = validation.check(junk, sc.schema)
    assert not report.parsed and not report.ok and report.errors and report.n_policies == 0


def test_reference_is_strictly_valid(sc):
    report = validation.check(sc.ref, sc.schema)
    assert report.ok and report.n_policies == 2, report


# 6. Enumeration blind spot.
def test_enum_blind_spot_without_c3(sc, universe):
    """Without c3, enumeration reports NO surplus for weak_same_wo, even though the policy is wrong.

    Enumeration only judges the requests it is shown. weak_same_wo drops the check
    `approval.wonum == input.wonum`. The only listed request that passes every other
    condition while breaking that one is c3 (an APPR approval by a human for one work
    order, used to close a different one at the same site). Remove c3 and no request in
    the universe can tell weak_same_wo apart from the reference, so surplus is the empty
    set. An empty enum surplus means "no witness among the listed requests", not "P is safe".

    symcc quantifies over every well-typed request instead of a list, so it finds a
    witness on its own (test_weak_does_not_imply_reference_on_close).
    """
    shrunk = universe.without({"c3"})
    assert "c3" not in shrunk.ids
    assert surplus(sc.weak("weak_same_wo"), sc.ref, shrunk, sc.schema) == set()


# EXTRA: errors are not denies. A schema-invalid request must raise, never count as a deny.
def test_invalid_request_raises(sc, universe):
    bad = universe.with_case("bad", {
        "action": {"type": "AOB::Action", "id": sc.close_action},
        "context": {"input": {"wonum": 1, sc.site_field: "MAIN"}},  # wonum must be a String
    })
    with pytest.raises(OracleError, match="bad"):
        allowed(sc.ref, bad, sc.schema)


# EXTRA: an invalid policy must raise, never evaluate to an empty allow-set.
def test_invalid_policy_raises(sc, universe, tmp_path):
    typo = tmp_path / "typo.cedar"
    typo.write_text(f'permit (principal, action == AOB::Action::"{sc.close_action}", resource)\n'
                    'when { context.input.site == "MAIN" };\n')  # `site` is not in either schema
    with pytest.raises(OracleError):
        allowed(typo, universe, sc.schema)


# 7. Symbolic backend: proofs over all well-typed requests. Skipped if cedar/cvc5 are absent.
@pytest.fixture(scope="module")
def symcc():
    try:
        sym.check_available()
    except sym.SymccUnavailable as e:
        pytest.skip(str(e))


def test_reference_implies_itself_everywhere(sc, symcc):
    results = sym.implies(sc.ref, sc.ref, sc.schema)
    assert len(results) == sc.n_actions
    assert sc.close_uid in {env.action for env in results}
    assert all(r == sym.VERIFIED for r in results.values()), results


@pytest.mark.parametrize("name", WEAK)
def test_weak_does_not_imply_reference_on_close(sc, name, symcc):
    results = sym.implies(sc.weak(name), sc.ref, sc.schema)
    (close_env,) = [env for env in results if env.action == sc.close_uid]
    assert results[close_env] != sym.VERIFIED
    assert sc.close_action in results[close_env]  # counterexample text names the request


@pytest.mark.parametrize("name", WEAK)
def test_counterexample_replays_in_cedarpy(sc, name, symcc):
    """Cross-check the backends: each symcc counterexample, rebuilt as a concrete request, must be
    allowed by P1 and denied by P2 under cedarpy. Guards against engine-version drift (cedarpy 4.12
    vs CLI 4.14) and against misparsing the counterexample text."""
    results = sym.implies(sc.weak(name), sc.ref, sc.schema)
    cexs = [r for r in results.values() if r != sym.VERIFIED]
    assert cexs, "expected at least one counterexample"
    for text in cexs:
        cex = sym.parse_counterexample(text)
        one = Universe({"cex": cex.request}, cex.entities, {})
        assert allowed(sc.weak(name), one, sc.schema) == {"cex"}, text
        assert allowed(sc.ref, one, sc.schema) == set(), text


@pytest.mark.parametrize("name", WEAK)
def test_weak_implies_reference_on_other_actions(sc, name, symcc):
    results = sym.implies(sc.weak(name), sc.ref, sc.schema)
    others = {env: r for env, r in results.items() if env.action != sc.close_uid}
    assert len(others) == sc.n_actions - 1
    assert all(r == sym.VERIFIED for r in others.values()), others


# Monotonicity (symbolic): the reference implies each weakening in every environment.
@pytest.mark.parametrize("name", WEAK)
def test_weakening_is_monotone_sym(sc, name, symcc):
    """If this fails, the weak file changed more than one condition (or narrowed something)."""
    results = sym.implies(sc.ref, sc.weak(name), sc.schema)
    assert len(results) == sc.n_actions
    assert all(r == sym.VERIFIED for r in results.values()), results
