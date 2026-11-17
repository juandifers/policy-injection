"""Text tally of Dogwood predicates (analysis aid, not a score)."""

from pathlib import Path

from pgi.analysis.dogwood_text import predicate_tally

T01 = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench" / "scenarios" / "t01_close_after_approval"


def test_gold_tally():
    t = predicate_tally((T01 / "gold.dw").read_text())
    (p,) = t["predicates"]
    assert p["action"] == "authority_get_approval" and p["kind"] == "response"
    assert p["fields"] == {"eventResource": "resource", "input.wonum": "context.input.wonum",
                           "input.site_id": "context.input.site_id", "output.decision": '"GRANTED"', "output.approver_kind": '"HUMAN"'}
    assert t["permit_actions"] == ["authority_get_approval", "close_workorder"] and t["forbid_actions"] == []
    assert t["literals"] == ['"GRANTED"', '"HUMAN"']


def test_statusflip_branch_and_forbid():
    text = (T01 / "weak_statusflip_branch.dw").read_text() + '\nforbid (principal, action == Drupe::Action::"approve_workorder", resource);\n'
    t = predicate_tally(text)
    assert t["predicates"][0]["action"] == "approve_workorder" and t["predicates"][0]["fields"]["output.result.typeChoice0"] == "_"
    assert t["forbid_actions"] == ["approve_workorder"]


def test_comments_and_prose_are_ignored():
    assert predicate_tally('// Drupe::Action::"x"::response{ a: "b" }\nnot a policy') == \
        {"predicates": [], "permit_actions": [], "forbid_actions": [], "literals": []}
