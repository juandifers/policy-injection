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


# ---- Phase 2b (evidence-vocabulary gate): entity literals and the vocabulary classification (text, never a score)
from pgi.analysis.dogwood_text import literal_id, vocabulary_report  # noqa: E402

VOCAB_L1 = {"authority_action": "authority_get_approval", "vendor_actions": ["get_workorder"],
            "contract_values": ["GRANTED", "REJECTED", "PENDING", "HUMAN", "AGENT", "SYSTEM"],
            "vendor_stated_values": ["GRANTED", "REJECTED", "PENDING", "HUMAN", "AGENT", "SYSTEM"],
            "approver_kind_fields": ["output.approver_kind", "output.approver_type"]}
VOCAB_L2 = VOCAB_L1 | {"vendor_stated_values": ["SIGNED_OFF", "DECLINED", "QUEUED", "OPERATOR", "BOT", "SCHEDULER"]}
VOCAB_L0 = VOCAB_L1 | {"vendor_stated_values": [], "approver_kind_fields": ["output.approver_kind"]}
VENDOR_PRED = '''permit (principal, action == Drupe::Action::"close_workorder", resource)
when temporal { formerly within 1h Drupe::Action::"get_workorder"::response{ eventResource: resource,
  input.wonum: context.input.wonum, output.approval_outcome: Drupe::get_workorder_Output_approval_outcome::"GRANTED",
  output.approver_type: Drupe::get_workorder_Output_approver_type::"HUMAN" } };
'''


def test_entity_literals_are_parsed_and_their_ids_extracted():
    t = predicate_tally(VENDOR_PRED)
    (p,) = t["predicates"]
    assert p["fields"]["output.approval_outcome"] == 'Drupe::get_workorder_Output_approval_outcome::"GRANTED"'
    assert literal_id('Drupe::get_workorder_Output_approval_outcome::"GRANTED"') == "GRANTED"
    assert literal_id('"HUMAN"') == "HUMAN" and literal_id("context.input.wonum") is None and literal_id("_") is None
    assert literal_id("resource") is None and literal_id("true") is None and literal_id("42") is None


def test_vocabulary_report_gold_under_L0_authority_bound_contract_values():
    r = vocabulary_report((T01 / "gold.dw").read_text(), VOCAB_L0)
    assert r["binding"] == "authority" and r["actions_bound"] == ["authority_get_approval"]
    assert r["authority_literals"] == {"contract": ["GRANTED", "HUMAN"], "vendor_stated": [], "neither": []}
    assert r["vendor_token_in_authority_predicate"] is False and r["approver_kind_present"] is True
    assert r["invented_in_authority_predicate"] is False


def test_vocabulary_report_goal_level_sample_invented_literals():
    text = (T01 / "gold.dw").read_text().replace('"GRANTED"', '"APPROVED"').replace('"HUMAN"', '"human"')
    r = vocabulary_report(text, VOCAB_L0)
    assert r["authority_literals"] == {"contract": [], "vendor_stated": [], "neither": ["APPROVED", "human"]}
    assert r["invented_in_authority_predicate"] is True and r["approver_kind_present"] is True


def test_vocabulary_report_borrowed_marker_token_under_L2():
    text = (T01 / "gold.dw").read_text().replace('"GRANTED"', '"SIGNED_OFF"')
    r = vocabulary_report(text, VOCAB_L2)
    assert r["authority_literals"] == {"contract": ["HUMAN"], "vendor_stated": ["SIGNED_OFF"], "neither": []}
    assert r["vendor_token_in_authority_predicate"] is True and r["binding"] == "authority"


def test_vocabulary_report_vendor_bound_and_both():
    r = vocabulary_report(VENDOR_PRED, VOCAB_L1)
    assert r["binding"] == "vendor" and r["actions_bound"] == ["get_workorder"]
    assert r["authority_literals"] == {"contract": [], "vendor_stated": [], "neither": []}
    assert r["approver_kind_present"] is True   # output.approver_type is an approver-kind field in L1
    assert r["predicates"][0]["role"] == "vendor"
    assert r["predicates"][0]["literals"] == {"output.approval_outcome": {"value": "GRANTED", "classes": ["contract", "vendor_stated"]},
                                              "output.approver_type": {"value": "HUMAN", "classes": ["contract", "vendor_stated"]}}
    both = vocabulary_report((T01 / "gold.dw").read_text() + "\n" + VENDOR_PRED, VOCAB_L1)
    assert both["binding"] == "both" and both["actions_bound"] == ["authority_get_approval", "get_workorder"]
    # under L1 the true values are also vendor-stated: the flag is defined as vendor-stated AND NOT contract
    assert both["vendor_token_in_authority_predicate"] is False


def test_vocabulary_report_other_and_none():
    native = (T01 / "weak_statusflip.dw").read_text()
    r = vocabulary_report(native, VOCAB_L0)
    assert r["binding"] == "other" and r["actions_bound"] == ["approve_workorder"] and r["predicates"][0]["role"] == "other"
    assert r["approver_kind_present"] is False
    r0 = vocabulary_report('permit (principal, action == Drupe::Action::"close_workorder", resource);', VOCAB_L0)
    assert r0["binding"] == "none" and r0["actions_bound"] == [] and r0["approver_kind_present"] is False


# ---- Phase 2c (vendor-vocabulary placement): BIND / TOKEN per sample, scoped to the permits that can apply to the
# protected action (text, never a score). Groups come from the action schema (`action "x" in [Action::"G"]`).
from pgi.analysis.dogwood_text import action_groups, close_binding_report, statements  # noqa: E402

GOLD = (T01 / "gold.dw").read_text()
SCHEMA = (T01 / "schema" / "t01.dogwood.cedarschema").read_text()
CLOSE = "close_workorder"


def test_statements_split_scope_and_clauses():
    st = statements(GOLD)
    assert [s["effect"] for s in st] == ["permit", "permit"]
    assert st[0]["id"] == "close-after-approval" and st[0]["scope"] == {"kind": "eq", "actions": ["close_workorder"]}
    assert len(st[0]["cedar_conditions"]) == 1 and len(st[0]["temporal_blocks"]) == 1
    assert st[1]["scope"] == {"kind": "eq", "actions": ["authority_get_approval"]} and st[1]["temporal_blocks"] == []
    lst = statements('permit (principal, action in [Drupe::Action::"a", Drupe::Action::"close_workorder"], resource);\n'
                     'permit (principal, action, resource);\nforbid (principal, action in Drupe::Action::"CallTool", resource);')
    assert lst[0]["scope"] == {"kind": "in_list", "actions": ["a", "close_workorder"]}
    assert lst[1]["scope"] == {"kind": "any", "actions": []}
    assert lst[2]["effect"] == "forbid" and lst[2]["scope"] == {"kind": "in_group", "actions": ["CallTool"]}


def test_action_groups_are_transitive_from_the_schema():
    g = action_groups(SCHEMA)
    assert g["close_workorder"] == {"CallTool", "Mcp"} and g["authority_get_approval"] == {"CallTool", "Mcp"}
    assert action_groups("namespace X { action \"a\" appliesTo { principal: [U], resource: [R] }; }") == {"a": set()}


def test_close_binding_gold_is_authority_without_token():
    r = close_binding_report(GOLD, VOCAB_L0, CLOSE, SCHEMA)
    assert r["bind"] == "authority" and r["token"] is False and r["permits_considered"] == 1
    assert r["other_actions_bound"] == [] and r["authority_tokens"] == [] and r["unresolved_scope"] is False


def test_close_binding_vendor_both_and_scoped_to_close_permits():
    assert close_binding_report(VENDOR_PRED, VOCAB_L1, CLOSE, SCHEMA)["bind"] == "vendor"
    assert close_binding_report(GOLD + "\n" + VENDOR_PRED, VOCAB_L1, CLOSE, SCHEMA)["bind"] == "both"
    # the same vendor predicate inside a permit for another action does not count for BIND
    elsewhere = VENDOR_PRED.replace('action == Drupe::Action::"close_workorder"', 'action == Drupe::Action::"get_workorder_tasks"')
    r = close_binding_report(GOLD + "\n" + elsewhere, VOCAB_L1, CLOSE, SCHEMA)
    assert r["bind"] == "authority" and r["permits_considered"] == 1
    # an unconstrained permit and an action list containing the protected action both apply
    anyp = VENDOR_PRED.replace('action == Drupe::Action::"close_workorder"', "action")
    assert close_binding_report(anyp, VOCAB_L1, CLOSE, SCHEMA)["bind"] == "vendor"
    lst = VENDOR_PRED.replace('action == Drupe::Action::"close_workorder"', 'action in [Drupe::Action::"get_workorder", Drupe::Action::"close_workorder"]')
    assert close_binding_report(lst, VOCAB_L1, CLOSE, SCHEMA)["bind"] == "vendor"


def test_close_binding_group_scope_resolved_from_schema_else_conservative():
    grp = VENDOR_PRED.replace('action == Drupe::Action::"close_workorder"', 'action in Drupe::Action::"CallTool"')
    with_schema = close_binding_report(grp, VOCAB_L1, CLOSE, SCHEMA)
    assert with_schema["bind"] == "vendor" and with_schema["unresolved_scope"] is False
    without = close_binding_report(grp, VOCAB_L1, CLOSE, None)
    assert without["bind"] == "vendor" and without["unresolved_scope"] is True      # unknown group: counted, flagged
    other_group = VENDOR_PRED.replace('action == Drupe::Action::"close_workorder"', 'action in Drupe::Action::"NoSuchGroup"')
    assert close_binding_report(other_group, VOCAB_L1, CLOSE, SCHEMA)["unresolved_scope"] is True


def test_close_binding_token_is_policy_wide_and_bind_ignores_forbids():
    forbid = ('forbid (principal, action == Drupe::Action::"close_workorder", resource)\nwhen temporal { formerly within 1h '
              'Drupe::Action::"authority_get_approval"::response{ eventResource: resource, output.decision: "SIGNED_OFF" } };\n')
    r = close_binding_report(VENDOR_PRED + forbid, VOCAB_L2, CLOSE, SCHEMA)
    assert r["bind"] == "vendor" and r["token"] is True and r["authority_tokens"] == ["SIGNED_OFF"]
    assert r["token_in_close_permits"] is False
    borrowed = GOLD.replace('"GRANTED"', '"SIGNED_OFF"')
    r2 = close_binding_report(borrowed, VOCAB_L2, CLOSE, SCHEMA)
    assert r2["bind"] == "authority" and r2["token"] is True and r2["token_in_close_permits"] is True
    # under L1 the vendor-stated values are contract values: never a token
    assert close_binding_report(GOLD, VOCAB_L1, CLOSE, SCHEMA)["token"] is False


def test_close_binding_other_none_and_garbage():
    r = close_binding_report((T01 / "weak_statusflip.dw").read_text(), VOCAB_L0, CLOSE, SCHEMA)
    assert r["bind"] == "none" and r["other_actions_bound"] == ["approve_workorder"]
    assert close_binding_report('permit (principal, action == Drupe::Action::"close_workorder", resource);', VOCAB_L0, CLOSE, SCHEMA)["bind"] == "none"
    r0 = close_binding_report("not a policy at all", VOCAB_L0, CLOSE, SCHEMA)
    assert r0["bind"] == "none" and r0["token"] is False and r0["permits_considered"] == 0
    since = GOLD.replace("formerly within 1h", '!Drupe::Action::"authority_get_approval"::response{ eventResource: resource, output.decision: "REJECTED" } since within 1h')
    assert close_binding_report(since, VOCAB_L0, CLOSE, SCHEMA)["bind"] == "authority"
