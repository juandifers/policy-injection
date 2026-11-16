"""Temporal backend: validates and replays Dogwood (.dw) policies against event traces. No LLM.

The judge is the Dogwood reference interpreter (crate `dogwood-language`), reached through the `pydogwood`
wheel, which mirrors the `dogwood` CLI's `validate` and `replay` commands one to one (docs/decisions.md,
2026-11-16). Conventions follow `pgi.oracle.enumeration`: file paths in, structured verdicts out, and any
error is raised, never read as a deny.

What the interpreter does silently, and what this module does about it (each verified, tests/test_temporal.py):
- `replay` of an INVALID policy denies every decision with no error  -> every replay validates first.
- an evaluation error, or a decision event without `scope(...)`, is a DENY with `errors` -> OracleError.
- non-increasing timestamps are accepted ("the interpreter does not check the timestamp contract") -> OracleError.
- an unknown action or an undeclared logged field in a trace is simply never matched. This cannot be
  checked here without a trace parser; the adequacy gate (gold must ALLOW the contract's allow traces) is
  what catches a dead trace.

Event schema: every entry point takes an optional `event_schema` (.dwschema path). None means Dogwood's
default (request/response/error, universal pin on `callerPrincipal`). AWS AgentCore's documented event
schema pins `sessionId` and names `eventPrincipal`/`eventResource` instead (docs/transfer-fidelity.md #5); a
scenario that wants that reading passes the file explicitly, and its action schema must then declare
`sessionId` in every action's context (the pin's right-hand side is `context.sessionId`).

Scoring unit: a trace is replayed whole and the verdict of its LAST decision event is the decision; the
earlier decision events (evidence calls, attempts) are history. A suite (`traces.yaml`) names traces by
stable id and carries the contract's expected decision for each, so allow-sets over a suite compose with
the same set arithmetic as the enumeration backend.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from pgi.oracle.errors import OracleError

_TS = re.compile(r"^@(-?\d+)\s")
_SUITE_KEYS = {"traces"}
_TRACE_KEYS = {"id", "file", "contract", "note"}
_CONTRACT = {"allow": True, "deny": False}


class TemporalUnavailable(RuntimeError):
    """The Dogwood interpreter (pydogwood) is not installed."""


def _dw():
    try:
        import pydogwood
    except ImportError as e:  # pragma: no cover - environment
        raise TemporalUnavailable("the temporal oracle needs `pydogwood` (uv group `dogwood`)") from e
    return pydogwood


def tool_versions() -> dict[str, str]:
    """Interpreter identity for run records: the wheel version and the Dogwood CLI version it mirrors."""
    from importlib.metadata import version

    return {"pydogwood": version("pydogwood"), "dogwood": _dw().DOGWOOD_VERSION}


@dataclass(frozen=True)
class TemporalValidationReport:
    """Outcome of `dogwood validate` (parse, lower, type-check against the action schema) on one file."""

    policy: str
    schema: str
    ok: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Verdict:
    """One decision event of a replay: `index` counts decision events, `timestamp` is the trace's `@ts`."""

    index: int
    timestamp: int
    allowed: bool
    determining_rules: tuple[int, ...]
    errors: tuple[str, ...]

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TraceSuite:
    """Traces by stable id, each with the contract's expected decision (True = allow)."""

    traces: dict[str, Path]
    contract: dict[str, bool]

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(self.traces)


@dataclass(frozen=True)
class AdequacyReport:
    """Can this suite tell the gold policy from each weakening, and does gold match the contract?"""

    gold_allowed: frozenset[str]
    gold_mismatches: frozenset[str]              # traces where gold != contract
    disagreements: dict[str, frozenset[str]]     # weakening -> traces where it differs from gold

    @property
    def adequate(self) -> bool:
        return not self.gold_mismatches and all(self.disagreements.values())

    def as_dict(self) -> dict:
        return {"gold_allowed": sorted(self.gold_allowed), "gold_mismatches": sorted(self.gold_mismatches),
                "disagreements": {k: sorted(v) for k, v in self.disagreements.items()}, "adequate": self.adequate}


def _messages(items: list[dict]) -> tuple[str, ...]:
    return tuple(i["message"] if isinstance(i, dict) else str(i) for i in items)


def _event_schema(event_schema: Path | None) -> str | None:
    return None if event_schema is None else Path(event_schema).read_text()


def check(policy: Path, schema: Path, event_schema: Path | None = None) -> TemporalValidationReport:
    """Validate one .dw file against one action schema; never raises for problems in the policy itself."""
    dw = _dw()
    text, schema_text = Path(policy).read_text(), Path(schema).read_text()
    try:
        out = dw.validate(text, policy_schema=schema_text, event_schema=_event_schema(event_schema), format="json")
    except dw.DogwoodError as e:
        out = str(e)
    try:
        report = json.loads(out)
    except json.JSONDecodeError as e:
        raise TemporalUnavailable(f"unparseable dogwood validate output: {out}") from e
    if "passed" in report:  # a validation report (passed or failed)
        errors, warnings = _messages(report["errors"]), _messages(report["warnings"])
        ok = bool(report["passed_without_warnings"]) and not errors and not warnings
    else:  # a fatal op error (syntax, macro, schema): one diagnostic
        errors, warnings, ok = _messages([report]), (), False
    return TemporalValidationReport(str(policy), str(schema), ok, errors, warnings)


def require_valid(policy: Path, schema: Path, event_schema: Path | None = None) -> TemporalValidationReport:
    """Raise OracleError unless the policy validates with no errors and no warnings."""
    report = check(policy, schema, event_schema)
    if not report.ok:
        raise OracleError(f"{policy} fails dogwood validation against {schema}: "
                          f"errors={list(report.errors)} warnings={list(report.warnings)}")
    return report


def _check_timestamps(trace: Path, text: str) -> None:
    """Strictly increasing `@ts` per line, which the interpreter requires but does not check."""
    stamps = [int(m.group(1)) for line in text.splitlines() if (m := _TS.match(line))]
    for a, b in zip(stamps, stamps[1:]):
        if b <= a:
            raise OracleError(f"{trace}: timestamps must be strictly increasing, got @{a} then @{b}")


def replay(policy: Path, schema: Path, trace: Path, event_schema: Path | None = None) -> tuple[Verdict, ...]:
    """Verdict per decision event, in trace order. Validates first; raises on any error."""
    dw = _dw()
    require_valid(policy, schema, event_schema)
    trace_text = Path(trace).read_text()
    _check_timestamps(Path(trace), trace_text)
    try:
        out = dw.replay(Path(policy).read_text(), policy_schema=Path(schema).read_text(), trace=trace_text,
                        event_schema=_event_schema(event_schema), format="json")
    except dw.DogwoodError as e:
        raise OracleError(f"{trace} under {policy}: {e}") from e
    verdicts = tuple(Verdict(v["index"], v["timestamp"], v["verdict"] == "allow",
                             tuple(v["determining_rules"]), tuple(v["errors"]))
                     for v in json.loads(out)["verdicts"])
    for v in verdicts:
        if v.errors:
            raise OracleError(f"{trace} under {policy}: decision {v.index} at @{v.timestamp} "
                              f"had evaluation errors {list(v.errors)} (not a deny)")
        if v.allowed != (v.determining_rules != ()):
            raise OracleError(f"{trace} under {policy}: verdict {v.allowed} with rules {v.determining_rules}")
    return verdicts


def decision(policy: Path, schema: Path, trace: Path, event_schema: Path | None = None) -> bool:
    """The decision of the trace's last decision event (the request being scored)."""
    verdicts = replay(policy, schema, trace, event_schema)
    if not verdicts:
        raise OracleError(f"{trace}: no decision event, nothing to score")
    return verdicts[-1].allowed


def load_suite(path: Path) -> TraceSuite:
    """Load traces.yaml: `traces: [{id, file, contract: allow|deny, note?}]`, files relative to it."""
    path = Path(path)
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("traces"), list) or not data["traces"]:
        raise OracleError(f"{path}: expected a mapping with a non-empty 'traces' list")
    if unknown := set(data) - _SUITE_KEYS:
        raise OracleError(f"{path}: unknown top-level keys {sorted(unknown)}")
    traces: dict[str, Path] = {}
    contract: dict[str, bool] = {}
    for entry in data["traces"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
            raise OracleError(f"{path}: every trace needs a non-empty string id, got {entry!r}")
        tid = entry["id"]
        if unknown := set(entry) - _TRACE_KEYS:
            raise OracleError(f"{path}: trace {tid!r}: unknown keys {sorted(unknown)}")
        if tid in traces:
            raise OracleError(f"{path}: duplicate trace id {tid!r}")
        if entry.get("contract") not in _CONTRACT:
            raise OracleError(f"{path}: trace {tid!r}: contract must be allow or deny, got {entry.get('contract')!r}")
        file = path.parent / str(entry.get("file", ""))
        if not entry.get("file") or not file.is_file():
            raise OracleError(f"{path}: trace {tid!r}: file {entry.get('file')!r} not found")
        traces[tid], contract[tid] = file, _CONTRACT[entry["contract"]]
    return TraceSuite(traces, contract)


def allowed(policy: Path, suite: TraceSuite, schema: Path, event_schema: Path | None = None) -> set[str]:
    """allow-set(policy) over a suite: the trace ids whose scored decision is ALLOW."""
    return {tid for tid, trace in suite.traces.items() if decision(policy, schema, trace, event_schema)}


def adequacy(gold: Path, weakenings: Mapping[str, Path], suite: TraceSuite, schema: Path,
             event_schema: Path | None = None) -> AdequacyReport:
    """Gold must equal the contract on every trace; every weakening must differ from gold on >= 1 trace."""
    gold_set = frozenset(allowed(gold, suite, schema, event_schema))
    mismatches = frozenset(tid for tid, want in suite.contract.items() if (tid in gold_set) != want)
    disagreements = {name: frozenset(allowed(path, suite, schema, event_schema) ^ gold_set)
                     for name, path in weakenings.items()}
    return AdequacyReport(gold_set, mismatches, disagreements)


def require_adequate(gold: Path, weakenings: Mapping[str, Path], suite: TraceSuite, schema: Path,
                     event_schema: Path | None = None) -> AdequacyReport:
    """`adequacy`, raising OracleError with the offending traces or weakenings."""
    report = adequacy(gold, weakenings, suite, schema, event_schema)
    if report.gold_mismatches:
        raise OracleError(f"gold {gold} disagrees with the contract on {sorted(report.gold_mismatches)}")
    if undetected := sorted(k for k, v in report.disagreements.items() if not v):
        raise OracleError(f"no trace distinguishes weakening(s) {undetected} from gold {gold}")
    return report
