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
SERVERS = ["wo", "iot"]

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


def generate(server: str) -> str:
    """The generated .cedarschema text for one server's pinned manifest."""
    pinned = json.loads((MANIFESTS / f"{server}.tools.json").read_text())
    result = generate_schema_or_raise(STUB.read_text(), json.dumps({"result": pinned}), config=CONFIG)
    return result["schema"]


def main(out: Path) -> None:
    """Write <server>.generated.cedarschema for each server and print its SHA-256."""
    out.mkdir(parents=True, exist_ok=True)
    for server in SERVERS:
        path = out / f"{server}.generated.cedarschema"
        if path.exists():
            raise SystemExit(f"{path} exists; generated schemas are never overwritten")
        path.write_text(generate(server))
        print(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DOMAIN / "schema")
    main(parser.parse_args().out)
