"""Generate one Cedar schema per pinned MCP manifest with cedar-policy-mcp-schema-generator 0.7.0.

    uv run --group schemagen python domains/assetopsbench/scripts/gen_schema.py [--out DIR]

Inputs are never modified. The pinned manifest is `{"tools": [...]}`; the generator only accepts a
JSON-RPC result (`{"result": {"tools": [...]}}`), a bare tool array, or a single tool, so the pinned
object is wrapped as `{"result": <pinned>}` in memory. Output files are never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cedar_mcp_schema_generator import generate_schema_or_raise

DOMAIN = Path(__file__).resolve().parents[1]
STUB = DOMAIN / "schema" / "stub.cedarschema"
MANIFESTS = DOMAIN / "manifests"
# Target name -> pinned manifests whose tools are passed to the generator together, in this order.
TARGETS = {"wo": ["wo"], "iot": ["iot"], "wo_iot": ["wo", "iot"]}

# Every setting the Python binding accepts, spelled out. These are the generator defaults;
# AWS AgentCore's settings are unknown (see docs/decisions.md).
CONFIG = {
    "includeOutputs": False,
    "objectsAsRecords": False,
    "eraseAnnotations": True,
    "flattenNamespaces": False,
    "numbersAsDecimal": False,
    "deduplicateEntityTypes": False,
}


def generate(target: str) -> str:
    """The generated .cedarschema text for one target (one or more pinned manifests' tools, concatenated)."""
    tools = []
    for server in TARGETS[target]:
        tools += json.loads((MANIFESTS / f"{server}.tools.json").read_text())["tools"]
    names = [t["name"] for t in tools]
    if len(names) != len(set(names)):
        raise SystemExit(f"{target}: tool names collide across servers: {sorted({n for n in names if names.count(n) > 1})}")
    result = generate_schema_or_raise(STUB.read_text(), json.dumps({"result": {"tools": tools}}), config=CONFIG)
    return result["schema"]


def main(out: Path, targets: list[str]) -> None:
    """Write <target>.generated.cedarschema for each target and print its SHA-256."""
    out.mkdir(parents=True, exist_ok=True)
    for server in targets:
        path = out / f"{server}.generated.cedarschema"
        if path.exists():
            raise SystemExit(f"{path} exists; generated schemas are never overwritten")
        path.write_text(generate(server))
        print(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DOMAIN / "schema")
    parser.add_argument("targets", nargs="*", help=f"subset of {list(TARGETS)} (default: all)")
    args = parser.parse_args()
    if unknown := set(args.targets) - set(TARGETS):
        parser.error(f"unknown targets {sorted(unknown)}; choose from {list(TARGETS)}")
    main(args.out, args.targets or list(TARGETS))
