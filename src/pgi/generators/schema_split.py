"""Split a generated Cedar/Dogwood action schema into top-level declarations, and a full schema into a fixed part and the
rest (Phase 3 split prompt layout). Text only; the validator and the oracle never see the split.

Why: the generator sorts declarations by name, so the declarations of an instance's own tools are interleaved with the
fixed MaintData ones, and every instance would have a different cached prefix. Part 1 is the schema generated from the
fixed manifest alone; part 2 is every declaration of the instance's full schema that is not in part 1, wrapped in the same
namespace. Both texts come from the same generator (and the same session link), so a fixed declaration is byte-identical in
both, which `split_schema` asserts: every part-1 declaration must occur unchanged in the full schema, and part 1 plus part 2
must equal the full schema as a set of declarations.
"""

from __future__ import annotations

import re

_NAMESPACE = re.compile(r"\A\s*namespace\s+([A-Za-z_][\w:]*)\s*\{", re.S)
_OPEN, _CLOSE = "{[(", "}])"


class SchemaSplitError(ValueError):
    """The schema text cannot be split, or the fixed part is not contained unchanged in the full schema."""


def declarations(schema_text: str) -> tuple[str, list[str]]:
    """(namespace name, top-level declarations in order), each declaration stripped and ending with `;`.

    Splits the namespace body on `;` at bracket depth 0, skipping string literals. Refuses a text that is not one
    `namespace X { ... }` block or whose body has trailing text after the last `;`.
    """
    m = _NAMESPACE.match(schema_text)
    if not m:
        raise SchemaSplitError("not a schema: expected `namespace <name> {` at the start")
    close = schema_text.rstrip().rfind("}")
    if close < m.end():
        raise SchemaSplitError("not a schema: no closing `}`")
    body = schema_text[m.end():close]
    out, depth, cur, i = [], 0, [], 0
    while i < len(body):
        ch = body[i]
        if ch == '"':
            j = body.find('"', i + 1)
            while j != -1 and body[j - 1] == "\\":
                j = body.find('"', j + 1)
            if j == -1:
                raise SchemaSplitError("unterminated string literal")
            cur.append(body[i:j + 1])
            i = j + 1
            continue
        cur.append(ch)
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth -= 1
            if depth < 0:
                raise SchemaSplitError("unbalanced brackets")
        elif ch == ";" and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        i += 1
    if "".join(cur).strip():
        raise SchemaSplitError(f"trailing text after the last declaration: {''.join(cur).strip()[:60]!r}")
    if depth != 0:
        raise SchemaSplitError("unbalanced brackets")
    return m.group(1), out


def _name(decl: str) -> str:
    return " ".join(decl.split()[:2]).rstrip(";")


def render(namespace: str, decls: list[str]) -> str:
    """Declarations back into one namespace block, in the generator's formatting (two-space indent)."""
    return f"namespace {namespace} {{\n" + "\n".join("  " + d for d in decls) + "\n}\n"


def split_schema(full_text: str, base_text: str) -> str:
    """Part 2: the declarations of `full_text` that are not in `base_text`, wrapped in the namespace.

    Raises SchemaSplitError unless both texts share one namespace, every base declaration occurs unchanged in the full
    text, and at least one declaration remains for part 2.
    """
    ns_full, full = declarations(full_text)
    ns_base, base = declarations(base_text)
    if ns_full != ns_base:
        raise SchemaSplitError(f"namespace differs: full {ns_full!r}, base {ns_base!r}")
    full_set = set(full)
    if missing := [d for d in base if d not in full_set]:
        raise SchemaSplitError(f"{len(missing)} base declaration(s) do not occur unchanged in the full schema; first: {_name(missing[0])}")
    base_set = set(base)
    part2 = [d for d in full if d not in base_set]
    if not part2:
        raise SchemaSplitError("no declaration left for part 2: the full schema equals the base schema")
    assert base_set | set(part2) == full_set
    return render(ns_full, part2)
