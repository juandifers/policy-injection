"""Link a generated schema with our trusted additions into one final schema.

    uv run python domains/assetopsbench/scripts/link_schema.py GENERATED TRUSTED OUT [--check]

Cedar 4.14.1 cannot do this itself: `cedar validate` takes one schema file, a namespace may appear
only once per file, and an action's context cannot be extended from another declaration. So:

1. Translate both files to Cedar's JSON schema form with `cedar translate-schema`.
2. Refuse if they share a namespace.
3. For each trusted common type annotated `@pgi_action("<ns>::<action>")` and
   `@pgi_context_attribute("<name>")`, add `<name>?: <type>` to that action's inline context record.
   Fail if the action is missing, its context is not an inline record, or the attribute exists.
4. Merge the namespaces (so trusted entity types, e.g. enums, are carried over) and translate back.

The logic lives in pgi.schemagen.link. The generated file is only read. With --check, compare
against OUT instead of writing it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pgi.schemagen import SchemaGenError
from pgi.schemagen import link as _link


def link(generated: Path, trusted: Path) -> str:
    """The final schema text (pgi.schemagen.link); exit loudly on failure."""
    try:
        return _link(generated, trusted)
    except SchemaGenError as e:
        sys.exit(str(e))


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
