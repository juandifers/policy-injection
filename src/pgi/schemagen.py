"""Cedar schema from MCP manifests, and linking our trusted additions into it. Domain-agnostic.

generate: cedar-policy-mcp-schema-generator 0.7.0 over the tools of one or more `{"tools": [...]}`
manifests, concatenated in order, with a stub schema. The pinned manifest form is wrapped as a
JSON-RPC result (`{"result": {"tools": [...]}}`) in memory, the only object form the generator accepts.
CONFIG spells out every setting the Python binding accepts; these are the generator defaults (AWS
AgentCore's settings are unknown; docs/decisions.md).

link: Cedar 4.14.1 cannot do this itself (`cedar validate` takes one schema file, a namespace may appear
only once per file, and an action's context cannot be extended from another declaration). So:
  1. translate both files to Cedar's JSON schema form with `cedar translate-schema`;
  2. refuse if they share a namespace;
  3. for each trusted common type annotated `@pgi_action("<ns>::<action>")` and
     `@pgi_context_attribute("<name>")`, add `<name>?: <type>` to that action's inline context record,
     failing if the action is missing, its context is not an inline record, or the attribute exists;
  4. merge the namespaces (so trusted entity types, e.g. enums, are carried over) and translate back.
Input files are only read.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path

CONFIG = {
    "includeOutputs": False,
    "objectsAsRecords": False,
    "eraseAnnotations": True,
    "flattenNamespaces": False,
    "numbersAsDecimal": False,
    "deduplicateEntityTypes": False,
}


# Second profile, for the temporal (Dogwood) track: Dogwood's own MCP generator (`dogwood schema mcp`,
# crate dogwood-language 1.1.0 via pydogwood). These are its fixed defaults, recorded here for the
# transfer-fidelity ledger; pydogwood.schema_mcp exposes no options, so nothing is passed. The template
# is Dogwood's embedded Drupe stub (namespace Drupe, principal User, resource Gateway), not ours.
DOGWOOD_PROFILE = {
    "include_outputs": True,            # context.output from each tool's outputSchema (temporal predicates read output.*)
    "encode_numbers_as_decimal": True,  # JSON number -> Cedar decimal (CONFIG above: opaque Number entity)
    "flatten_namespaces": True,         # Drupe::Action::"<tool>"
}


class SchemaGenError(Exception):
    """Schema generation or linking failed."""


def _tools(manifests: list[Path], targets: Mapping[Path | str, str] | None = None) -> list[dict]:
    """The tools of these `{"tools": [...]}` manifests, concatenated in order; tool names must be unique.

    `targets` (Phase 3): manifest path -> gateway target name; every tool of that manifest is renamed `<Target>___<tool>`
    in memory (the AgentCore gateway form). Manifests on disk keep their unprefixed names. Every key must name one of the
    manifests.
    """
    targets = {Path(k).resolve(): v for k, v in (targets or {}).items()}
    if unknown := set(targets) - {Path(p).resolve() for p in manifests}:
        raise SchemaGenError(f"targets name manifests not in the list: {sorted(str(p) for p in unknown)}")
    tools = []
    for path in manifests:
        target = targets.get(Path(path).resolve())
        for tool in json.loads(Path(path).read_text())["tools"]:
            tools.append({**tool, "name": f"{target}___{tool['name']}"} if target else tool)
    names = [t["name"] for t in tools]
    if len(names) != len(set(names)):
        raise SchemaGenError(f"tool names collide across manifests: {sorted({n for n in names if names.count(n) > 1})}")
    return tools


def generate(stub: Path, manifests: list[Path]) -> str:
    """The generated .cedarschema text for the tools of these manifests, in order (Cedar track, CONFIG)."""
    from cedar_mcp_schema_generator import generate_schema_or_raise  # dependency group `schemagen`

    return generate_schema_or_raise(Path(stub).read_text(), json.dumps({"result": {"tools": _tools(manifests)}}),
                                    config=CONFIG)["schema"]


def generate_dogwood(manifests: list[Path], targets: Mapping[Path | str, str] | None = None) -> str:
    """The Dogwood-generated .cedarschema text for these manifests' tools (temporal track, DOGWOOD_PROFILE).

    `targets` renames the tools of the named manifests to `<Target>___<tool>` before generation (see `_tools`); without
    it the output is byte-identical to before (every pinned schema).
    """
    import pydogwood  # dependency group `dogwood`

    try:
        return pydogwood.schema_mcp(json.dumps({"result": {"tools": _tools(manifests, targets)}}))
    except pydogwood.DogwoodError as e:
        raise SchemaGenError(f"dogwood schema mcp failed: {e}") from e


def _cedar(*args: str) -> str:
    """Run the cedar CLI and return stdout; raise on failure."""
    proc = subprocess.run(["cedar", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SchemaGenError(f"cedar {' '.join(args)} failed:\n{proc.stdout}{proc.stderr}")
    return proc.stdout


def _to_json(path: Path) -> dict:
    """A Cedar-syntax schema file as Cedar's JSON schema form."""
    return json.loads(_cedar("translate-schema", "--direction", "cedar-to-json", "--schema", str(path)))


def link_session_id(generated: Path) -> str:
    """Temporal track: the generated schema with `sessionId: String` declared in every action's context.

    AWS AgentCore's temporal event schema pins `sessionId = context.sessionId`, so an action schema scored under
    it must declare the field (docs/transfer-fidelity.md #5). Same route as `link`: Cedar's own translator,
    JSON edit, translate back. Refuses an action whose context is not an inline record or already has the field.
    """
    js = _to_json(generated)
    for ns, body in js.items():
        for name, decl in body.get("actions", {}).items():
            ctx = decl.get("appliesTo", {}).get("context")
            if not ctx or ctx.get("type") != "Record":
                raise SchemaGenError(f"{ns}::{name}: context is not an inline record: {ctx}")
            if "sessionId" in ctx["attributes"]:
                raise SchemaGenError(f"{ns}::{name}: context already declares sessionId (already linked?)")
            ctx["attributes"]["sessionId"] = {"type": "String"}
    with tempfile.NamedTemporaryFile("w", suffix=".cedarschema.json", delete=False) as f:
        json.dump(js, f)
    return _cedar("translate-schema", "--direction", "json-to-cedar", "--schema", f.name)


def link(generated: Path, trusted: Path) -> str:
    """The final schema text: generated + trusted types + annotated context attributes."""
    gen, tr = _to_json(generated), _to_json(trusted)
    if shared := set(gen) & set(tr):
        raise SchemaGenError(f"trusted file reuses generated namespace(s) {sorted(shared)}")
    for ns, body in tr.items():
        for name, ty in body.get("commonTypes", {}).items():
            ann = ty.get("annotations", {})
            if "pgi_action" not in ann:
                continue
            target_ns, _, action = ann["pgi_action"].rpartition("::")
            attr = ann["pgi_context_attribute"]
            decl = gen.get(target_ns, {}).get("actions", {}).get(action)
            if decl is None:
                raise SchemaGenError(f"{ns}::{name}: action {ann['pgi_action']!r} not in {generated}")
            ctx = decl.get("appliesTo", {}).get("context")
            if not ctx or ctx.get("type") != "Record":
                raise SchemaGenError(f"{ns}::{name}: context of {ann['pgi_action']} is not an inline record: {ctx}")
            if attr in ctx["attributes"]:
                raise SchemaGenError(f"{ns}::{name}: {ann['pgi_action']} context already has {attr!r}")
            ctx["attributes"][attr] = {"type": f"{ns}::{name}", "required": False}
    with tempfile.NamedTemporaryFile("w", suffix=".cedarschema.json", delete=False) as f:
        json.dump({**gen, **tr}, f)
    return _cedar("translate-schema", "--direction", "json-to-cedar", "--schema", f.name)
