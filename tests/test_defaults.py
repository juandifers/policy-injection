"""Default-reliance detector: a policy relies on a vendor default when it allows a request with a defaulted
field omitted, yet denies some explicit value of that field (other inputs fixed)."""

import json
from pathlib import Path

import pytest
import yaml

from pgi.analysis.defaults import default_reliance, summarize_reliance
from pgi.oracle.enumeration import load_universe
from pgi.oracle.errors import OracleError
from pgi.runs.snapshot import load_snapshot

SCHEMA = """namespace T {
  entity User;
  entity Server;
  type fInput = { site: String, flag?: Bool, mode?: String, n?: Long };
  action "f" appliesTo { principal: User, resource: Server, context: { input: fInput } };
  action "g" appliesTo { principal: User, resource: Server, context: { input: fInput } };
}
"""
MANIFEST = {"tools": [
    {"name": "f", "inputSchema": {"type": "object", "required": ["site"], "properties": {
        "site": {"type": "string"},
        "flag": {"type": "boolean", "default": True},
        "mode": {"type": "string", "enum": ["a", "b"], "default": "a"},
        "n": {"type": "integer", "default": 5}}}},
]}
UNIVERSE = {
    "principal": {"type": "T::User", "id": "u"},
    "resource": {"type": "T::Server", "id": "s"},
    "cases": [
        {"id": "flag_true", "action": {"type": "T::Action", "id": "f"}, "context": {"input": {"site": "M", "flag": True}}},
        {"id": "flag_false", "action": {"type": "T::Action", "id": "f"}, "context": {"input": {"site": "M", "flag": False}}},
        {"id": "mode_a", "action": {"type": "T::Action", "id": "f"}, "context": {"input": {"site": "M", "mode": "a"}}},
        {"id": "n_7", "action": {"type": "T::Action", "id": "f"}, "context": {"input": {"site": "M", "n": 7}}},
        {"id": "plain", "action": {"type": "T::Action", "id": "f"}, "context": {"input": {"site": "M"}}},
        {"id": "g_flag", "action": {"type": "T::Action", "id": "g"}, "context": {"input": {"site": "M", "flag": True}}},
    ],
}
F = 'permit (principal, action == T::Action::"f", resource) when { context.input.site == "M"'


@pytest.fixture
def env(tmp_path):
    (tmp_path / "s.cedarschema").write_text(SCHEMA)
    (tmp_path / "m.json").write_text(json.dumps(MANIFEST))
    (tmp_path / "u.yaml").write_text(yaml.safe_dump(UNIVERSE))

    def run(policy: str, manifest: dict | None = None):
        (tmp_path / "p.cedar").write_text(policy)
        if manifest is not None:
            (tmp_path / "m.json").write_text(json.dumps(manifest))
        return default_reliance(tmp_path / "p.cedar", load_universe(tmp_path / "u.yaml"),
                                tmp_path / "s.cedarschema", {"srv": tmp_path / "m.json"})
    return run


def _by(rows):
    return {(r["case"], r["field"]): r for r in rows}


def test_absent_means_true_is_reliance(env):
    rows = _by(env(F + ' && (if context.input has flag then context.input.flag == true else true) };'))
    r = rows[("flag_true", "flag")]
    assert (r["tool"], r["default"], r["set_value"], r["omitted_allowed"]) == ("f", True, True, True)
    assert r["alternatives"] == [{"value": False, "allowed": False}]
    assert r["verdict"] == "relies"


def test_requiring_the_field_present_is_not_reliance(env):
    rows = _by(env(F + ' && context.input has flag && context.input.flag == true };'))
    assert rows[("flag_true", "flag")]["verdict"] == "omission_denied"


def test_ignoring_the_field_is_unconstrained_not_reliance(env):
    rows = _by(env(F + ' };'))
    assert rows[("flag_true", "flag")]["verdict"] == "unconstrained"
    assert rows[("mode_a", "mode")]["verdict"] == "unconstrained"


def test_enum_members_are_alternatives(env):
    rows = _by(env(F + ' && (if context.input has mode then context.input.mode == "a" else true) };'))
    r = rows[("mode_a", "mode")]
    assert r["alternatives"] == [{"value": "b", "allowed": False}]
    assert r["verdict"] == "relies"


def test_field_with_no_alternative_value_is_untestable(env):
    # n is a Long with no enum and takes only the value 7 in the universe: nothing to compare against.
    rows = _by(env(F + ' && (if context.input has n then context.input.n == 7 else true) };'))
    r = rows[("n_7", "n")]
    assert (r["omitted_allowed"], r["alternatives"], r["verdict"]) == (True, [], "untestable")


def test_only_allowed_cases_and_defaulted_fields_set_explicitly_are_examined(env):
    rows = env(F + ' && (if context.input has flag then context.input.flag == true else true) };')
    # flag_false is denied; plain sets no defaulted field; site has no default; g has no manifest tool.
    assert sorted((r["case"], r["field"]) for r in rows) == [("flag_true", "flag"), ("mode_a", "mode"), ("n_7", "n")]


def test_values_from_other_cases_of_the_same_tool_are_alternatives(env):
    manifest = json.loads(json.dumps(MANIFEST))
    del manifest["tools"][0]["inputSchema"]["properties"]["mode"]["enum"]
    rows = _by(env(F + ' && (if context.input has mode then context.input.mode == "a" else true) };', manifest))
    # no enum, and mode is "a" in every case of f, so there is nothing to compare against
    assert rows[("mode_a", "mode")]["verdict"] == "untestable"


def test_omitting_a_field_the_schema_requires_fails_loudly(env):
    manifest = json.loads(json.dumps(MANIFEST))
    manifest["tools"][0]["inputSchema"]["properties"]["site"]["default"] = "M"
    with pytest.raises(OracleError):
        env(F + ' };', manifest)


def test_tool_declared_by_two_servers_is_an_error(env, tmp_path):
    (tmp_path / "m2.json").write_text(json.dumps(MANIFEST))
    (tmp_path / "p.cedar").write_text(F + ' };')
    with pytest.raises(OracleError):
        default_reliance(tmp_path / "p.cedar", load_universe(tmp_path / "u.yaml"), tmp_path / "s.cedarschema",
                         {"a": tmp_path / "m.json", "b": tmp_path / "m2.json"})


def test_summary_counts_relying_rows_by_tool_and_field(env):
    rows = env(F + ' && (if context.input has flag then context.input.flag == true else true)'
                   ' && (if context.input has mode then context.input.mode == "a" else true) };')
    s = summarize_reliance(rows)
    assert s["relies"] == 2
    assert s["by_field"] == {"f.flag": 1, "f.mode": 1}
    assert s["verdicts"] == {"relies": 2, "untestable": 1}


BASELINE = Path(__file__).resolve().parents[1] / "runs" / "20261113T155356Z-clean"


@pytest.mark.parametrize("sample,verdict", [("sample_00", "relies"), ("sample_03", "omission_denied")])
def test_baseline_s02_open_only(sample, verdict):
    # sample_00: `if has open_only then open_only == true else true`; sample_03: `has open_only && == true`.
    inp = load_snapshot(BASELINE / "inputs" / "s02_site_scoped_reads")
    policy = BASELINE / "s02_site_scoped_reads" / "sondera" / sample / "policy.cedar"
    rows = default_reliance(policy, load_universe(inp.universe), inp.schema_path,
                            dict(zip(inp.servers, inp.manifest_paths)))
    [row] = [r for r in rows if r["field"] == "open_only"]
    assert (row["case"], row["tool"], row["default"], row["verdict"]) == \
        ("assigned_main_open", "get_my_assigned_workorders", True, verdict)
