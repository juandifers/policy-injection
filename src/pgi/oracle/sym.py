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


# Counterexample parsing. symcc prints counterexamples in Cedar expression syntax, not JSON:
#   principal: T::"id", action: A::Action::"name", resource: T::"id"
#   context: {k: "s", r: {e: T::"id"}}
#   entities: [ T::"id", ... ]
# The parser accepts only strings, longs, bools, sets, records and entity UIDs, and raises on anything
# else (extension values, entities printed with attributes), so an unparsed shape can never be guessed.

_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", "0": "\0", "'": "'", '"': '"'}
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_LONG = re.compile(r"-?[0-9]+")


class CounterexampleParseError(SymccError):
    """symcc printed a counterexample this parser does not recognise."""


@dataclass(frozen=True)
class Counterexample:
    """A symcc counterexample rebuilt as a concrete cedarpy request plus its entity store."""

    request: dict
    entities: list[dict]


class _Reader:
    """Strict recursive-descent reader over one Cedar value literal."""

    def __init__(self, text: str) -> None:
        self.text, self.pos = text, 0

    def fail(self, what: str) -> CounterexampleParseError:
        """An error naming the position and the unparsed remainder."""
        return CounterexampleParseError(f"{what} at {self.pos}: {self.text[self.pos:self.pos + 40]!r}")

    def skip_ws(self) -> None:
        """Advance past whitespace."""
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def expect(self, token: str) -> None:
        """Consume a literal token or raise."""
        self.skip_ws()
        if not self.text.startswith(token, self.pos):
            raise self.fail(f"expected {token!r}")
        self.pos += len(token)

    def peek(self, token: str) -> bool:
        """True if the next non-space text starts with token."""
        self.skip_ws()
        return self.text.startswith(token, self.pos)

    def done(self) -> None:
        """Raise unless all input was consumed."""
        self.skip_ws()
        if self.pos != len(self.text):
            raise self.fail("trailing input")

    def string(self) -> str:
        """A double-quoted Cedar string with escapes."""
        self.expect('"')
        out = []
        while self.pos < len(self.text):
            ch = self.text[self.pos]
            self.pos += 1
            if ch == '"':
                return "".join(out)
            if ch != "\\":
                out.append(ch)
                continue
            esc = self.text[self.pos:self.pos + 1]
            self.pos += 1
            if esc in _ESCAPES:
                out.append(_ESCAPES[esc])
            elif esc == "u" and (m := re.match(r"\{([0-9a-fA-F]{1,6})\}", self.text[self.pos:])):
                out.append(chr(int(m[1], 16)))
                self.pos += m.end()
            else:
                raise self.fail(f"unknown escape \\{esc}")
        raise self.fail("unterminated string")

    def uid(self) -> dict:
        """An entity UID like A::B::"id", as {"type", "id"}."""
        self.skip_ws()
        path = []
        while m := _IDENT.match(self.text, self.pos):
            path.append(m[0])
            self.pos = m.end()
            self.expect("::")
            if self.peek('"'):
                return {"type": "::".join(path), "id": self.string()}
        raise self.fail("expected entity UID")

    def value(self) -> object:
        """Any supported Cedar value literal."""
        self.skip_ws()
        if self.peek('"'):
            return self.string()
        if self.peek("{"):
            return self.record()
        if self.peek("["):
            return self.items(self.value)
        if m := _LONG.match(self.text, self.pos):
            self.pos = m.end()
            return int(m[0])
        for word, val in (("true", True), ("false", False)):
            if re.match(rf"{word}\b", self.text[self.pos:]):
                self.pos += len(word)
                return val
        if _IDENT.match(self.text, self.pos) and not re.match(r"[A-Za-z_][A-Za-z0-9_]*\s*\(", self.text[self.pos:]):
            return {"__entity": self.uid()}
        raise self.fail("unsupported value")

    def record(self) -> dict:
        """A record literal {k: v, ...}; keys are identifiers or strings."""
        self.expect("{")
        out: dict = {}
        while not self.peek("}"):
            key = self.string() if self.peek('"') else self.ident()
            self.expect(":")
            out[key] = self.value()
            if not self.peek("}"):
                self.expect(",")
        self.expect("}")
        return out

    def items(self, item) -> list:
        """A bracketed, comma-separated list (trailing comma allowed)."""
        self.expect("[")
        out = []
        while not self.peek("]"):
            out.append(item())
            if not self.peek("]"):
                self.expect(",")
        self.expect("]")
        return out

    def ident(self) -> str:
        """A bare identifier."""
        self.skip_ws()
        if not (m := _IDENT.match(self.text, self.pos)):
            raise self.fail("expected identifier")
        self.pos = m.end()
        return m[0]


def parse_counterexample(text: str) -> Counterexample:
    """Rebuild a symcc counterexample (the text implies() returns) as a concrete request and entity store."""
    _, sep, body = text.partition("Counterexample found:")
    if not sep:
        raise CounterexampleParseError(f"no counterexample in:\n{text}")
    lines = body.strip().splitlines()
    try:
        head, ctx, ents = lines[0], lines[1], "\n".join(lines[2:])
    except IndexError:
        raise CounterexampleParseError(f"expected principal, context and entities lines:\n{body}") from None
    r = _Reader(head)
    request = {}
    for i, key in enumerate(("principal", "action", "resource")):
        if i:
            r.expect(",")
        r.expect(f"{key}:")
        request[key] = r.uid()
    r.done()
    r = _Reader(ctx)
    r.expect("context:")
    request["context"] = r.record()
    r.done()
    r = _Reader(ents)
    r.expect("entities:")
    uids = r.items(r.uid)
    r.done()
    entities = [{"uid": u, "attrs": {}, "parents": []} for u in uids if not u["type"].split("::")[-1] == "Action"]
    return Counterexample(request, entities)
