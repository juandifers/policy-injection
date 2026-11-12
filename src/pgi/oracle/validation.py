"""Strict policy validation: schema errors AND warnings both count as failures.

cedarpy reports errors only; it drops warnings such as "policy is impossible: evaluates to false
for all valid requests". So validity needs the Cedar CLI with `--deny-warnings` as well. A policy
is `ok` only if both engines accept it.

- check(): returns a ValidationReport; used for generated policies, where validity is measured.
- require_valid(): raises OracleError unless ok; used for references and hand-written files.

Limitation: when a policy set has errors, `cedar validate` does not report its warnings, so a
report's warnings are complete only when it has no errors.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import cedarpy

from pgi.oracle.errors import OracleError


class ValidationUnavailable(RuntimeError):
    """The Cedar CLI needed for strict validation is missing or behaved unexpectedly."""


@dataclass(frozen=True)
class ValidationReport:
    """Outcome of strict validation of one policy file against one schema."""

    policy: str
    schema: str
    ok: bool
    parsed: bool
    n_policies: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    cedarpy_errors: tuple[str, ...]

    def as_dict(self) -> dict:
        """JSON-ready form."""
        return asdict(self)


def _cedar() -> str:
    """Path of the cedar CLI, or raise ValidationUnavailable."""
    path = shutil.which("cedar")
    if path is None:
        raise ValidationUnavailable("strict validation needs the `cedar` CLI on PATH (cedar-policy-cli)")
    return path


def _diagnostics(node: dict, top: bool = True) -> list[tuple[str, str]]:
    """Flatten one CLI JSON diagnostic into (severity, text) pairs, following `related` recursively."""
    msgs = node["causes"] if top and node.get("causes") else [node["message"]]
    out = [(node["severity"], f"{m} ({node['help']})" if node.get("help") else m) for m in msgs]
    for rel in node.get("related", []):
        out += _diagnostics(rel, top=False)
    return out


def _cli(policy: Path, schema: Path) -> tuple[bool, list[str], list[str]]:
    """Run `cedar validate --deny-warnings`; return (parsed, errors, warnings)."""
    proc = subprocess.run([_cedar(), "validate", "--deny-warnings", "--error-format", "json",
                           "--schema", str(schema), "--policies", str(policy)], capture_output=True, text=True)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    try:
        nodes = [json.loads(l) for l in lines]
    except json.JSONDecodeError as e:
        raise ValidationUnavailable(f"unparseable cedar validate output (exit {proc.returncode}): {proc.stdout}{proc.stderr}") from e
    if proc.returncode == 0:
        if any(n.get("severity") != "advice" for n in nodes):
            raise ValidationUnavailable(f"cedar validate exited 0 but reported: {proc.stdout}")
        return True, [], []
    if proc.returncode not in (1, 3) or not nodes:
        raise ValidationUnavailable(f"cedar validate exited {proc.returncode}: {proc.stdout}{proc.stderr}")
    pairs = [p for n in nodes for p in _diagnostics(n)]
    parsed = not any(n.get("message") == "failed to parse policy set" for n in nodes)
    errors = [t for s, t in pairs if s == "error"]
    warnings = [t for s, t in pairs if s == "warning"]
    if not errors and not warnings:
        raise ValidationUnavailable(f"cedar validate failed without a diagnostic: {proc.stdout}")
    return parsed, errors, warnings


def _count_policies(text: str) -> int:
    """Number of static policies and templates in the text, or 0 if it does not parse."""
    try:
        d = json.loads(cedarpy.policies_to_json_str(text))
    except Exception:
        return 0
    return len(d.get("staticPolicies", {})) + len(d.get("templates", {}))


def check(policy: Path, schema: Path) -> ValidationReport:
    """Strictly validate one policy file; never raises for problems in the policy itself."""
    text, schema_text = Path(policy).read_text(), Path(schema).read_text()
    py = cedarpy.validate_policies(text, schema_text)
    parsed, errors, warnings = _cli(Path(policy), Path(schema))
    py_errors = tuple(str(e) for e in py.errors)
    ok = parsed and not errors and not warnings and py.validation_passed
    return ValidationReport(str(policy), str(schema), ok, parsed, _count_policies(text),
                            tuple(errors), tuple(warnings), py_errors)


def require_valid(policy: Path, schema: Path) -> ValidationReport:
    """Strictly validate a hand-written policy file; raise OracleError on any error or warning."""
    report = check(policy, schema)
    if not report.ok:
        raise OracleError(f"{policy} fails strict validation: errors={list(report.errors)} "
                          f"warnings={list(report.warnings)} cedarpy={list(report.cedarpy_errors)}")
    return report
