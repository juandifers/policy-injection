"""Contract of the temporal oracle backend (`pgi.oracle.temporal`): Dogwood validate + replay, no LLM.

Known answers come from the Dogwood repository's own `read_after_login_success` bundle (fixture README has
the provenance). Everything else is derived from that bundle by one edit, so the tests need no domain.

Invariant 6 (errors are not denies) is the point of most tests here: the reference interpreter silently
denies on an invalid policy, an evaluation error, a decision event without scope, and accepts
non-increasing timestamps. The wrapper must turn each of those into OracleError.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pgi.oracle import temporal
from pgi.oracle.errors import OracleError

FIX = Path(__file__).parent / "fixtures" / "dogwood" / "read_after_login_success"
POLICY, SCHEMA, TRACE = FIX / "policy.dw", FIX / "schema.cedarschema", FIX / "trace.log"
LINES = TRACE.read_text().splitlines()  # 0: alice login ok, 1: alice read, 2: bob login failed, 3: bob read


def write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def trace(tmp_path: Path, name: str, *idx: int) -> Path:
    return write(tmp_path, name, "\n".join(LINES[i] for i in idx) + "\n")


def weakening(tmp_path: Path, name: str, old: str, new: str) -> Path:
    text = POLICY.read_text()
    assert old in text
    return write(tmp_path, name, text.replace(old, new))


# ---------------------------------------------------------------- known-answer: the bundled example


def test_verdict_stream_matches_the_bundles_expected_out():
    verdicts = temporal.replay(POLICY, SCHEMA, TRACE)
    assert [(v.index, v.timestamp, v.allowed, v.determining_rules) for v in verdicts] == \
        [(0, 100, True, (0,)), (1, 300, False, ())]
    assert all(v.errors == () for v in verdicts)
    # expected.out is the interpreter's human rendering of the same stream.
    expected = [l.split(": ")[1].split()[0] for l in (FIX / "expected.out").read_text().splitlines() if l]
    assert ["ALLOW" if v.allowed else "DENY" for v in verdicts] == expected


def test_decision_is_the_verdict_of_the_last_decision_event(tmp_path):
    assert temporal.decision(POLICY, SCHEMA, TRACE) is False  # bob's read at @300
    assert temporal.decision(POLICY, SCHEMA, trace(tmp_path, "alice.log", 0, 1)) is True


def test_check_accepts_the_example_and_reports_a_rejected_policy(tmp_path):
    ok = temporal.check(POLICY, SCHEMA)
    assert ok.ok and ok.errors == () and ok.warnings == ()
    bad = weakening(tmp_path, "bad.dw", "output.result: true", "output.resultx: true")
    report = temporal.check(bad, SCHEMA)
    assert not report.ok
    assert any("output.resultx" in e for e in report.errors)
    with pytest.raises(OracleError, match="resultx"):
        temporal.require_valid(bad, SCHEMA)


# ---------------------------------------------------------------- errors are not denies


def test_replay_refuses_an_invalid_policy_instead_of_denying(tmp_path):
    """The interpreter replays an invalid policy as all-DENY with no error; the wrapper must not."""
    bad = weakening(tmp_path, "bad.dw", "output.result: true", "output.resultx: true")
    with pytest.raises(OracleError, match="resultx"):
        temporal.replay(bad, SCHEMA, TRACE)


def test_evaluation_error_raises(tmp_path):
    """A Cedar clause reading a context field the request does not carry is an error, not a deny."""
    pol = weakening(tmp_path, "doc.dw", "when temporal {", 'when { context.input.document == "doc1" }\nwhen temporal {')
    assert temporal.decision(pol, SCHEMA, trace(tmp_path, "ok.log", 0, 1)) is True
    broken = LINES[1].replace('request_context(input: { document: "doc1", user: "alice" })',
                              'request_context(input: { user: "alice" })')
    t = write(tmp_path, "noctx.log", LINES[0] + "\n" + broken + "\n")
    with pytest.raises(OracleError, match="attribute `document`"):
        temporal.replay(pol, SCHEMA, t)


def test_decision_event_without_scope_raises(tmp_path):
    noscope = LINES[1].replace('scope(principal: Drupe::OAuthUser::"alice", resource: Drupe::Gateway::"gw1") ', "")
    t = write(tmp_path, "noscope.log", LINES[0] + "\n" + noscope + "\n")
    with pytest.raises(OracleError, match="no principal in scope"):
        temporal.replay(POLICY, SCHEMA, t)


def test_unparseable_trace_raises(tmp_path):
    t = write(tmp_path, "garbage.log", TRACE.read_text() + "@400 garbage\n")
    with pytest.raises(OracleError, match="trace parse"):
        temporal.replay(POLICY, SCHEMA, t)


def test_trace_without_a_decision_event_has_no_decision(tmp_path):
    history_only = trace(tmp_path, "history.log", 0)
    assert temporal.replay(POLICY, SCHEMA, history_only) == ()
    with pytest.raises(OracleError, match="no decision event"):
        temporal.decision(POLICY, SCHEMA, history_only)


def test_non_increasing_timestamps_raise(tmp_path):
    """The interpreter does not check the timestamp contract (docs, 04-temporal-expressions); we do."""
    with pytest.raises(OracleError, match="timestamps"):
        temporal.replay(POLICY, SCHEMA, trace(tmp_path, "back.log", 1, 0))
    with pytest.raises(OracleError, match="timestamps"):
        temporal.replay(POLICY, SCHEMA, write(tmp_path, "dup.log", LINES[0] + "\n" + LINES[0].replace('"u1"', '"u9"') + "\n"))


# ---------------------------------------------------------------- trace suites: allow-sets over traces


def suite_yaml(tmp_path: Path, contract_bob: str = "deny") -> Path:
    trace(tmp_path, "alice.log", 0, 1)
    trace(tmp_path, "bob.log", 2, 3)
    return write(tmp_path, "traces.yaml", yaml.safe_dump({"traces": [
        {"id": "alice", "file": "alice.log", "contract": "allow", "note": "login succeeded"},
        {"id": "bob", "file": "bob.log", "contract": contract_bob, "note": "login failed"},
    ]}))


def test_load_suite_and_allowed(tmp_path):
    suite = temporal.load_suite(suite_yaml(tmp_path))
    assert suite.ids == frozenset({"alice", "bob"})
    assert suite.contract == {"alice": True, "bob": False}
    assert suite.traces["bob"] == tmp_path / "bob.log"
    assert temporal.allowed(POLICY, suite, SCHEMA) == {"alice"}


@pytest.mark.parametrize("edit", [
    lambda s: s["traces"].append({"id": "alice", "file": "alice.log", "contract": "deny"}),  # duplicate id
    lambda s: s["traces"][0].update(contract="maybe"),                                       # bad contract
    lambda s: s["traces"][0].update(file="missing.log"),                                     # missing file
    lambda s: s["traces"][0].update(extra=1),                                                # unknown key
    lambda s: s["traces"][0].pop("contract"),                                                # no contract
])
def test_load_suite_rejects_malformed_suites(tmp_path, edit):
    path = suite_yaml(tmp_path)
    data = yaml.safe_load(path.read_text())
    edit(data)
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(OracleError):
        temporal.load_suite(path)


# ---------------------------------------------------------------- mutation adequacy gate


def test_adequacy_gold_matches_contract_and_every_weakening_is_caught(tmp_path):
    suite = temporal.load_suite(suite_yaml(tmp_path))
    weak = weakening(tmp_path, "weak_outcome.dw", "output.result: true", "output.result: _")
    report = temporal.adequacy(POLICY, {"outcome": weak}, suite, SCHEMA)
    assert report.gold_allowed == frozenset({"alice"})
    assert report.gold_mismatches == frozenset()
    assert report.disagreements == {"outcome": frozenset({"bob"})}
    assert report.adequate
    temporal.require_adequate(POLICY, {"outcome": weak}, suite, SCHEMA)


def test_adequacy_flags_a_weakening_no_trace_distinguishes(tmp_path):
    suite = temporal.load_suite(suite_yaml(tmp_path))
    same = weakening(tmp_path, "same.dw", "// a response predicate", "// renamed comment only")
    report = temporal.adequacy(POLICY, {"noop": same}, suite, SCHEMA)
    assert report.disagreements == {"noop": frozenset()}
    assert not report.adequate
    with pytest.raises(OracleError, match="noop"):
        temporal.require_adequate(POLICY, {"noop": same}, suite, SCHEMA)


def test_adequacy_flags_gold_disagreeing_with_the_contract(tmp_path):
    suite = temporal.load_suite(suite_yaml(tmp_path, contract_bob="allow"))
    report = temporal.adequacy(POLICY, {}, suite, SCHEMA)
    assert report.gold_mismatches == frozenset({"bob"})
    assert not report.adequate


def test_adequacy_does_not_swallow_an_invalid_weakening(tmp_path):
    suite = temporal.load_suite(suite_yaml(tmp_path))
    bad = weakening(tmp_path, "bad.dw", "output.result: true", "output.resultx: true")
    with pytest.raises(OracleError, match="resultx"):
        temporal.adequacy(POLICY, {"bad": bad}, suite, SCHEMA)


# ---------------------------------------------------------------- event schema: AWS-shaped session pin

# AWS AgentCore's documented temporal event schema (policy-temporal-authoring, "Event schema: fields you can
# reference"): pin on sessionId, fields eventPrincipal/eventResource. Dogwood's default pins callerPrincipal instead.
AGENTCORE_SHAPED = """
decision event <A>::request {
    ...inputs(A), eventPrincipal: principalType(A), eventResource: resourceType(A), requestId: String,
    pin sessionId: String = context.sessionId,
}
event <A>::response {
    ...inputs(A), ...outputs(A), eventPrincipal: principalType(A), eventResource: resourceType(A), requestId: String,
    pin sessionId: String = context.sessionId,
}
event <A>::error {
    ...inputs(A), eventPrincipal: principalType(A), eventResource: resourceType(A), requestId: String,
    pin sessionId: String = context.sessionId,
}
"""


def session_event(line: str, sid: str) -> str:
    line = line.replace("callerPrincipal", "eventPrincipal").replace("callerResource", "eventResource")
    line = line.replace('requestId: "', f'sessionId: "{sid}", requestId: "')
    return line.replace("request_context(", f'request_context(sessionId: "{sid}", ')


def test_event_schema_switches_the_pin_from_principal_to_session(tmp_path):
    ev = write(tmp_path, "agentcore.dwschema", AGENTCORE_SHAPED)
    # The pin's right-hand side is context.sessionId, so every action's context must declare it.
    sch = write(tmp_path, "schema.cedarschema",
                SCHEMA.read_text().replace("system: SystemContext", "sessionId: String,\n      system: SystemContext"))
    with pytest.raises(OracleError, match="sessionId"):
        temporal.require_valid(POLICY, SCHEMA, ev)   # the unmodified action schema lacks the pinned field
    assert temporal.check(POLICY, sch, ev).ok
    same = write(tmp_path, "same.log", session_event(LINES[0], "s1") + "\n" + session_event(LINES[1], "s1") + "\n")
    other = write(tmp_path, "other.log", session_event(LINES[0], "s1") + "\n" + session_event(LINES[1], "s2") + "\n")
    assert temporal.decision(POLICY, sch, same, ev) is True
    assert temporal.decision(POLICY, sch, other, ev) is False
    # Under the default schema the same two traces (with caller* names) are judged by principal, not session.
    assert temporal.decision(POLICY, SCHEMA, trace(tmp_path, "default.log", 0, 1)) is True


# ---------------------------------------------------------------- provenance for run records


def test_tool_versions_name_the_interpreter():
    v = temporal.tool_versions()
    assert v["pydogwood"] == "0.1.1"
    assert v["dogwood"] == "1.1.0"
