"""Link a generated schema with our trusted additions into one final schema.

    uv run python domains/assetopsbench/scripts/link_schema.py GENERATED TRUSTED OUT [--check]

Cedar 4.14.1 cannot do this itself: `cedar validate` takes one schema file, a namespace may appear
only once per file, and an action's context cannot be extended from another declaration. So:

1. Translate both files to Cedar's JSON schema form with `cedar translate-schema`.
2. Refuse if they share a namespace.
3. For each trusted common type annotated `@pgi_action("<ns>::<action>")` and
   `@pgi_context_attribute("<name>")`, add `<name>?: <type>` to that action's inline context record.
   Fail if the action is missing, its context is not an inline record, or the attribute exists.
4. Merge the namespaces and translate back to Cedar syntax.

The generated file is only read. With --check, compare against OUT instead of writing it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def cedar(*args: str) -> str:
    """Run the cedar CLI and return stdout; exit loudly on failure."""
    proc = subprocess.run(["cedar", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"cedar {' '.join(args)} failed:\n{proc.stdout}{proc.stderr}")
    return proc.stdout


def to_json(path: Path) -> dict:
    """A Cedar-syntax schema file as Cedar's JSON schema form."""
    return json.loads(cedar("translate-schema", "--direction", "cedar-to-json", "--schema", str(path)))


def link(generated: Path, trusted: Path) -> str:
    """The final schema text: generated + trusted types + annotated context attributes."""
    gen, tr = to_json(generated), to_json(trusted)
    if shared := set(gen) & set(tr):
        sys.exit(f"trusted file reuses generated namespace(s) {sorted(shared)}")
    for ns, body in tr.items():
        for name, ty in body.get("commonTypes", {}).items():
            ann = ty.get("annotations", {})
            if "pgi_action" not in ann:
                continue
            target_ns, _, action = ann["pgi_action"].rpartition("::")
            attr = ann["pgi_context_attribute"]
            decl = gen.get(target_ns, {}).get("actions", {}).get(action)
            if decl is None:
                sys.exit(f"{ns}::{name}: action {ann['pgi_action']!r} not in {generated}")
            ctx = decl.get("appliesTo", {}).get("context")
            if not ctx or ctx.get("type") != "Record":
                sys.exit(f"{ns}::{name}: context of {ann['pgi_action']} is not an inline record: {ctx}")
            if attr in ctx["attributes"]:
                sys.exit(f"{ns}::{name}: {ann['pgi_action']} context already has {attr!r}")
            ctx["attributes"][attr] = {"type": f"{ns}::{name}", "required": False}
    with tempfile.NamedTemporaryFile("w", suffix=".cedarschema.json", delete=False) as f:
        json.dump({**gen, **tr}, f)
    return cedar("translate-schema", "--direction", "json-to-cedar", "--schema", f.name)


def main() -> None:
    """Write (or with --check, verify) the linked schema."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("generated", type=Path)
    p.add_argument("trusted", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--check", action="store_true", help="fail unless OUT equals a fresh link")
    args = p.parse_args()
    text = link(args.generated, args.trusted)
    if args.check:
        if args.out.read_text() != text:
            sys.exit(f"{args.out} differs from link({args.generated}, {args.trusted})")
        print(f"ok: {args.out} == link({args.generated.name}, {args.trusted.name})")
    elif args.out.exists():
        sys.exit(f"{args.out} exists; rerun with --check, or delete it deliberately")
    else:
        args.out.write_text(text)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
