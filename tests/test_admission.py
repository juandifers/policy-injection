"""Phase 2c A5: deterministic admission checker for temporal evidence policies. No LLM. The catalogue is a trusted file
beside the written contract (README), derived from the contract text, not from gold. Fail closed: any construct the checker
does not model rejects the policy with a reason. Forbids are ignored. Behaviour is NOT consulted: the checker reads text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pgi.analysis.admission import check_policy, check_run, load_catalogue

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
T01 = DOMAIN / "scenarios" / "t01_close_after_approval"
ARMS = T01 / "arms"
RUNS = Path(__file__).resolve().parents[1] / "runs"
GOLD = (T01 / "gold.dw").read_text()
SCHEMA = (T01 / "schema" / "t01.dogwood.cedarschema").read_text()
AUTH = ('formerly within 1h Drupe::Action::"authority_get_approval"::response{ eventResource: resource, '
        'input.wonum: context.input.wonum, input.site_id: context.input.site_id, output.decision: "GRANTED", output.approver_kind: "HUMAN" }')
VEND = ('formerly within 1h Drupe::Action::"get_workorder"::response{ eventResource: resource, input.wonum: context.input.wonum, '
        'input.site_id: context.input.site_id, output.approval_outcome: Drupe::get_workorder_Output_approval_outcome::"SIGNED_OFF" }')
LOOKUP = 'permit (principal, action == Drupe::Action::"authority_get_approval", resource);\n'


def close(cond: str, scope: str = 'action == Drupe::Action::"close_workorder"') -> str:
    return f"permit (principal, {scope}, resource)\nwhen temporal {{ {cond} }};\n" + LOOKUP


@pytest.fixture(scope="module")
def cat():
    return load_catalogue(T01 / "admission.catalogue.yaml")


def test_catalogue_is_the_contract_not_gold(cat):
    assert cat["protected_action"] == "close_workorder"
    assert cat["evidence"] == {"action": "authority_get_approval", "kind": "response", "max_window": "1h"}
    assert cat["correlations"] == ["site_id", "wonum"]
    assert cat["authorizing_values"] == {"decision": "GRANTED", "approver_kind": "HUMAN"}
    text = (T01 / "admission.catalogue.yaml").read_text()
    assert "README" in text and "gold" not in text.lower().replace("not from gold", "")


def test_admits_gold_and_typed_gold(cat):
    for text in (GOLD, (ARMS / "typed" / "gold.dw").read_text()):
        r = check_policy(text, cat, SCHEMA)
        assert r["admitted"] is True and r["reasons"] == [] and r["vacuous"] is False, r
        (p,) = r["permits"]
        assert p["verdict"] == "admitted" and len(p["evidence"]) == 1
        assert p["extra_conjuncts"] == ["cedar: when"] and p["evidence"][0]["extra_fields"] == ["eventResource"]


@pytest.mark.parametrize("name,needle", [
    ("approver", "output.approver_kind"), ("outcome", "output.decision"), ("binding", "input.wonum"), ("window", "24h"),
    ("attempt", "request"), ("vendorflag", "get_workorder"), ("statusflip", "approve_workorder"), ("statusflip_branch", "approve_workorder"),
])
def test_rejects_every_weakened_variant_with_a_reason(cat, name, needle):
    r = check_policy((T01 / f"weak_{name}.dw").read_text(), cat, SCHEMA)
    assert r["admitted"] is False and r["reasons"], name
    assert any(needle in reason for reason in r["reasons"]), (name, r["reasons"])


def test_rejects_every_mutant_of_every_arm(cat):
    records = [json.loads((ARMS / f).read_text()) for f in ("arms.json", "arms-2c.json")]
    n = 0
    for rec in records:
        for arm, entry in rec["arms"].items():
            for mutant in entry["mutants"]:
                r = check_policy((ARMS / arm / "mutants" / f"{mutant}.dw").read_text(), cat, SCHEMA)
                assert r["admitted"] is False and r["reasons"], (arm, mutant)
                n += 1
    assert n >= 12


def test_rejects_unconditional_permits(cat):
    for scope in ('action == Drupe::Action::"close_workorder"', "action", 'action in [Drupe::Action::"close_workorder", Drupe::Action::"get_workorder"]',
                  'action in Drupe::Action::"CallTool"'):
        r = check_policy(f"permit (principal, {scope}, resource);\n", cat, SCHEMA)
        assert r["admitted"] is False and any("no temporal evidence clause" in x for x in r["reasons"]), scope
    r = check_policy('permit (principal, action == Drupe::Action::"close_workorder", resource) when { context.input.site_id == "MAIN" };', cat, SCHEMA)
    assert r["admitted"] is False and any("no temporal evidence clause" in x for x in r["reasons"])


def test_rejects_authority_or_vendor_in_both_forms(cat):
    two_permits = close(AUTH) + close(VEND)
    r = check_policy(two_permits, cat, SCHEMA)
    assert r["admitted"] is False and len(r["permits"]) == 2
    assert [p["verdict"] for p in r["permits"]] == ["admitted", "rejected"]
    assert any("get_workorder" in x for x in r["reasons"])
    textual_or = close(f"({AUTH}) || ({VEND})")      # not valid Dogwood, but the checker is fail-closed on text
    r2 = check_policy(textual_or, cat, SCHEMA)
    assert r2["admitted"] is False and any("get_workorder" in x or "branch" in x for x in r2["reasons"])


def test_extra_conjuncts_are_admitted_and_reported(cat):
    neg = ('!(formerly within 1h Drupe::Action::"close_workorder"::response{ eventResource: resource, input.wonum: context.input.wonum })')
    r = check_policy(close(f"{AUTH} && {neg}"), cat, SCHEMA)
    assert r["admitted"] is True
    assert any(x.startswith("negated:") for x in r["permits"][0]["extra_conjuncts"])
    both = check_policy(close(f"{AUTH} && {VEND}"), cat, SCHEMA)     # vendor as an EXTRA restriction: admitted, reported
    assert both["admitted"] is True and any("get_workorder" in x for x in both["permits"][0]["extra_conjuncts"])
    two_blocks = f'permit (principal, action == Drupe::Action::"close_workorder", resource)\nwhen temporal {{ {AUTH} }}\nwhen temporal {{ {VEND} }};\n' + LOOKUP
    assert check_policy(two_blocks, cat, SCHEMA)["admitted"] is True
    stronger = check_policy(close(AUTH.replace("eventResource: resource, ", "eventResource: resource, eventPrincipal: principal, ")), cat, SCHEMA)
    assert stronger["admitted"] is True and stronger["permits"][0]["evidence"][0]["extra_fields"] == ["eventPrincipal", "eventResource"]


def test_since_and_previous_forms_count_when_their_evidence_side_conforms(cat):
    rej = 'Drupe::Action::"authority_get_approval"::response{ eventResource: resource, input.wonum: context.input.wonum, output.decision: "REJECTED" }'
    body = AUTH.replace("formerly within 1h ", "")
    assert check_policy(close(f"!{rej} since within 1h {body}"), cat, SCHEMA)["admitted"] is True
    assert check_policy(close(f"previous within 30m {body}"), cat, SCHEMA)["admitted"] is True
    r = check_policy(close(f"!{body} since within 1h {rej}"), cat, SCHEMA)      # evidence side is the REJECTED record
    assert r["admitted"] is False and any("output.decision" in x for x in r["reasons"])


def test_window_limit_and_entity_forms(cat):
    assert check_policy(close(AUTH.replace("1h", "30m")), cat, SCHEMA)["admitted"] is True
    assert check_policy(close(AUTH.replace("1h", "3600s")), cat, SCHEMA)["admitted"] is True
    r = check_policy(close(AUTH.replace("1h", "2h")), cat, SCHEMA)
    assert r["admitted"] is False and any("2h" in x and "1h" in x for x in r["reasons"])
    r = check_policy(close(AUTH.replace("1h", "3601s")), cat, SCHEMA)
    assert r["admitted"] is False
    ent = AUTH.replace('"GRANTED"', 'Drupe::authority_get_approval_Output_decision::"GRANTED"').replace('"HUMAN"', 'Drupe::authority_get_approval_Output_approver_kind::"HUMAN"')
    assert check_policy(close(ent), cat, SCHEMA)["admitted"] is True
    bad = AUTH.replace('"GRANTED"', 'Drupe::authority_get_approval_Output_decision::"SIGNED_OFF"')
    r = check_policy(close(bad), cat, SCHEMA)
    assert r["admitted"] is False and any("SIGNED_OFF" in x for x in r["reasons"])
    assert check_policy(close(AUTH.replace('"GRANTED"', '"APPROVED"').replace('"HUMAN"', '"human"')), cat, SCHEMA)["admitted"] is False
    assert check_policy(close(AUTH.replace('"HUMAN"', "_")), cat, SCHEMA)["admitted"] is False      # wildcard is not an authorizing value


def test_unmodeled_constructs_fail_closed(cat):
    count = ('exists (n: Long). (count for (t: Timepoint). where (formerly within 1h Drupe::Action::"authority_get_approval"::response{ '
             'eventResource: resource, tp(t) })) == n && n > 0')
    r = check_policy(close(f"{AUTH} && {count}"), cat, SCHEMA)
    assert r["admitted"] is False and any("unmodeled" in x for x in r["reasons"])
    r = check_policy(close(f"{AUTH} && somethingElse"), cat, SCHEMA)
    assert r["admitted"] is False and any("unmodeled" in x for x in r["reasons"])
    # a permit over an action group the schema does not declare: cannot tell whether it applies -> rejected
    r = check_policy(close(AUTH, 'action in Drupe::Action::"NoSuchGroup"'), cat, SCHEMA)
    assert r["admitted"] is False and any("group" in x for x in r["reasons"])
    # a declared group containing the protected action applies and can be admitted
    assert check_policy(close(AUTH, 'action in Drupe::Action::"CallTool"'), cat, SCHEMA)["admitted"] is True
    # without the schema no group can be resolved
    assert check_policy(close(AUTH, 'action in Drupe::Action::"CallTool"'), cat, None)["admitted"] is False


def test_forbids_ignored_and_vacuous_policy_flagged(cat):
    forbid = 'forbid (principal, action == Drupe::Action::"close_workorder", resource)\nwhen temporal { ' + VEND + ' };\n'
    r = check_policy(GOLD + forbid, cat, SCHEMA)
    assert r["admitted"] is True and len(r["permits"]) == 1
    v = check_policy(LOOKUP, cat, SCHEMA)
    assert v["admitted"] is True and v["vacuous"] is True and v["permits"] == []
    assert check_policy("", cat, SCHEMA)["vacuous"] is True


def test_check_run_over_a_phase_2b_run_rejects_every_invented_literal_policy(cat):
    run = RUNS / "20261118T181007Z-temporal-clean-t01-goal-level-v2"
    r = check_run(run, cat)
    assert r["run_id"] == run.name and r["arm"] == "v2" and set(r["generators"]) == {"naive", "sondera"}
    for gen, rows in r["generators"].items():
        assert len(rows) == 20 and all(not row["admitted"] for row in rows), gen
        assert all(any("output.decision" in x or "output.approver_kind" in x for x in row["reasons"]) for row in rows), gen
        assert all(row["policy_sha256"] and row["sample"] == i for i, row in enumerate(rows))
