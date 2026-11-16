"""Generate one Cedar schema per pinned MCP manifest.

    uv run --group schemagen python domains/assetopsbench/scripts/gen_schema.py [--out DIR] [TARGET...]
    uv run --group dogwood   python domains/assetopsbench/scripts/gen_schema.py --profile dogwood wo

Profiles (pgi.schemagen): `cedar` (default) is cedar-policy-mcp-schema-generator 0.7.0 with CONFIG and our stub,
written as <target>.generated.cedarschema; `dogwood` is Dogwood's own generator with DOGWOOD_PROFILE (outputs on,
numbers as decimal), written as <target>.dogwood.generated.cedarschema.

Inputs are never modified. The pinned manifest is `{"tools": [...]}`; the generator only accepts a
JSON-RPC result (`{"result": {"tools": [...]}}`), a bare tool array, or a single tool, so the pinned
object is wrapped as `{"result": <pinned>}` in memory. Output files are never overwritten.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from pgi.schemagen import CONFIG, DOGWOOD_PROFILE, SchemaGenError  # noqa: F401  (every generator setting, spelled out)
from pgi.schemagen import generate as _generate
from pgi.schemagen import generate_dogwood as _generate_dogwood

DOMAIN = Path(__file__).resolve().parents[1]
STUB = DOMAIN / "schema" / "stub.cedarschema"
MANIFESTS = DOMAIN / "manifests"
# Target name -> pinned manifests whose tools are passed to the generator together, in this order.
TARGETS = {"wo": ["wo"], "iot": ["iot"], "wo_iot": ["wo", "iot"]}


SUFFIX = {"cedar": ".generated.cedarschema", "dogwood": ".dogwood.generated.cedarschema"}


def generate(target: str, profile: str = "cedar") -> str:
    """The generated .cedarschema text for one target and profile, over its pinned manifests."""
    manifests = [MANIFESTS / f"{s}.tools.json" for s in TARGETS[target]]
    try:
        return _generate(STUB, manifests) if profile == "cedar" else _generate_dogwood(manifests)
    except SchemaGenError as e:
        raise SystemExit(f"{target}: {e}")


def main(out: Path, targets: list[str], profile: str = "cedar") -> None:
    """Write <target><suffix> for each target and print its SHA-256."""
    out.mkdir(parents=True, exist_ok=True)
    for server in targets:
        path = out / f"{server}{SUFFIX[profile]}"
        if path.exists():
            raise SystemExit(f"{path} exists; generated schemas are never overwritten")
        path.write_text(generate(server, profile))
        print(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DOMAIN / "schema")
    parser.add_argument("--profile", choices=sorted(SUFFIX), default="cedar")
    parser.add_argument("targets", nargs="*", help=f"subset of {list(TARGETS)} (default: all)")
    args = parser.parse_args()
    if unknown := set(args.targets) - set(TARGETS):
        parser.error(f"unknown targets {sorted(unknown)}; choose from {list(TARGETS)}")
    main(args.out, args.targets or list(TARGETS), args.profile)
