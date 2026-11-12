"""Symbolic backend: a thin subprocess wrapper over `cedar symcc` (needs the CLI's `analyze` feature and cvc5).

Results hold over every well-typed request in an environment, not just a listed universe.
`cedar symcc` exits 0 both when a property holds and when it does not, so the verdict is
parsed from stdout; anything unrecognised raises SymccError.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

VERIFIED = "verified"
TIMEOUT_S = 120

_VERDICT = re.compile(r"^\S+ Policy set 1 implies policy set 2: (VERIFIED|DOES NOT HOLD)$")


class SymccUnavailable(RuntimeError):
    """The cedar CLI with symcc, or the cvc5 solver, is not installed or not configured."""


class SymccError(RuntimeError):
    """symcc ran but failed, or produced output this wrapper does not recognise."""


@dataclass(frozen=True)
class Env:
    """A request environment: one principal type, one action UID, one resource type."""

    principal_type: str
    action: str
    resource_type: str


def check_available() -> str:
    """Return the cedar binary path, or raise SymccUnavailable naming what is missing."""
    cedar = shutil.which("cedar")
    if cedar is None:
        raise SymccUnavailable("`cedar` CLI not on PATH (need cedar-policy-cli with the `analyze` feature)")
    cvc5 = os.environ.get("CVC5")
    if not cvc5 or not os.access(cvc5, os.X_OK):
        raise SymccUnavailable(f"$CVC5 must point to an executable cvc5 1.3.1 binary, got {cvc5!r}")
    probe = subprocess.run([cedar, "symcc", "--help"], capture_output=True, text=True)
    if probe.returncode != 0:
        raise SymccUnavailable(f"`cedar symcc` unavailable (CLI built without `analyze`?): {probe.stderr.strip()}")
    return cedar


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run the cedar CLI with colour off; raise SymccError on a non-zero exit."""
    proc = subprocess.run([check_available(), *args], capture_output=True, text=True,
                          timeout=TIMEOUT_S, env={**os.environ, "NO_COLOR": "1"})
    if proc.returncode != 0:
        raise SymccError(f"cedar {' '.join(args)} exited {proc.returncode}:\n{proc.stdout}{proc.stderr}")
    return proc


def environments(schema: Path) -> list[Env]:
    """Every (principal type, action, resource type) the schema allows, via translate-schema."""
    out = _run(["translate-schema", "--direction", "cedar-to-json-with-resolved-types",
                "--schema", str(schema)]).stdout
    envs = []
    for namespace, body in json.loads(out).items():
        prefix = f"{namespace}::" if namespace else ""
        for name, action in body.get("actions", {}).items():
            applies = action.get("appliesTo") or {}
            uid = f"{prefix}Action::{json.dumps(name)}"
            envs += [Env(p, uid, r) for p in applies.get("principalTypes", [])
                     for r in applies.get("resourceTypes", [])]
    if not envs:
        raise SymccError(f"{schema} defines no request environments")
    return sorted(envs, key=lambda e: (e.action, e.principal_type, e.resource_type))


def implies_in(env: Env, policies1: Path, policies2: Path, schema: Path) -> str:
    """In one environment: VERIFIED if allow-set(policies1) ⊆ allow-set(policies2), else the counterexample text."""
    out = _run(["symcc", "--principal-type", env.principal_type, "--action", env.action,
                "--resource-type", env.resource_type, "--schema", str(schema),
                "--counterexample", "--error-format", "plain",
                "implies", "--policies1", str(policies1), "--policies2", str(policies2)]).stdout.strip()
    match = _VERDICT.match(out.splitlines()[0] if out else "")
    if match and match[1] == "VERIFIED":
        return VERIFIED
    if match and "Counterexample found:" in out:
        return out
    raise SymccError(f"unrecognised symcc output for {env}:\n{out}")


def implies(policies1: Path, policies2: Path, schema: Path) -> dict[Env, str]:
    """For every environment in the schema: VERIFIED if policies1 implies policies2, else the counterexample."""
    return {env: implies_in(env, policies1, policies2, schema) for env in environments(schema)}
