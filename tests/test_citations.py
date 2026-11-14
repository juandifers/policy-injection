"""Intent citations: every action a reference permits is justified in reference.md by a quote from intent.md."""

from pathlib import Path

import pytest

from pgi.analysis.citations import check, parse_citations, permitted_actions

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
SCENARIOS = ["s01_close_after_approval", "s02_site_scoped_reads", "s03_create_at_main"]

INTENT = "# Intent\n\n- It may list MAIN's work orders.\n- It may close a work order only at MAIN.\n"
POLICY = """
permit (principal, action == AOB::Action::"list_workorders", resource);
permit (principal, action in [AOB::Action::"close_workorder", AOB::Action::"get_workorder"], resource)
when { context.input.site_id == "MAIN" };
forbid (principal, action == AOB::Action::"approve_workorder", resource);
"""


def _write(tmp_path, policy, md, intent=INTENT):
    (tmp_path / "reference.cedar").write_text(policy)
    (tmp_path / "reference.md").write_text(md)
    (tmp_path / "intent.md").write_text(intent)
    return tmp_path / "reference.cedar", tmp_path / "reference.md", tmp_path / "intent.md"


def _md(*lines):
    return "# ref\n\nprose\n\n## Intent citations\n" + "".join(f"{l}\n" for l in lines) + "\n## Later section\n- `x`: \"not a citation\"\n"


def test_permitted_actions_reads_eq_and_in_and_ignores_forbids(tmp_path):
    ref, _, _ = _write(tmp_path, POLICY, _md())
    assert permitted_actions(ref) == {"list_workorders", "close_workorder", "get_workorder"}


def test_unconstrained_action_scope_is_a_problem(tmp_path):
    ref, md, intent = _write(tmp_path, "permit (principal, action, resource);", _md())
    assert any("every action" in p for p in check(ref, md, intent))


def test_parse_citations_only_reads_its_section_and_allows_several_quotes():
    cites = parse_citations(_md('- `list_workorders`: "list MAIN\'s work orders"',
                                '- `close_workorder`: "close a work order" · "only at MAIN"'))
    assert cites == {"list_workorders": ["list MAIN's work orders"],
                     "close_workorder": ["close a work order", "only at MAIN"]}


def test_all_cited_with_substrings_passes(tmp_path):
    md = _md('- `list_workorders`: "list MAIN\'s work orders"',
             '- `close_workorder`: "close a work order only at MAIN"',
             '- `get_workorder`: "MAIN\'s work orders"')
    assert check(*_write(tmp_path, POLICY, md)) == []


def test_missing_citation_fails(tmp_path):
    md = _md('- `list_workorders`: "list MAIN\'s work orders"', '- `close_workorder`: "close a work order"')
    problems = check(*_write(tmp_path, POLICY, md))
    assert problems == ["get_workorder: permitted but has no intent quote"]


def test_quote_not_in_intent_fails(tmp_path):
    md = _md('- `list_workorders`: "list every site"', '- `close_workorder`: "close a work order"',
             '- `get_workorder`: "MAIN\'s work orders"')
    problems = check(*_write(tmp_path, POLICY, md))
    assert problems == ['list_workorders: quote not in intent.md: "list every site"']


def test_quote_match_is_exact_and_case_sensitive(tmp_path):
    md = _md('- `list_workorders`: "List MAIN\'s work orders"', '- `close_workorder`: "close a work order"',
             '- `get_workorder`: "MAIN\'s work orders"')
    assert len(check(*_write(tmp_path, POLICY, md))) == 1


def test_citation_for_an_action_not_permitted_is_stale(tmp_path):
    md = _md('- `list_workorders`: "list MAIN\'s work orders"', '- `close_workorder`: "close a work order"',
             '- `get_workorder`: "MAIN\'s work orders"', '- `approve_workorder`: "close a work order"')
    assert check(*_write(tmp_path, POLICY, md)) == ["approve_workorder: cited but not permitted by the reference"]


def test_missing_section_fails(tmp_path):
    problems = check(*_write(tmp_path, POLICY, "# ref\n\nno citations here\n"))
    assert problems == ["reference.md has no '## Intent citations' section"]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_permitted_action_is_cited_from_the_intent(scenario):
    folder = DOMAIN / "scenarios" / scenario
    assert check(folder / "reference.cedar", folder / "reference.md", folder / "intent.md") == []
