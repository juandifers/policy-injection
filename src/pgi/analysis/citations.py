"""Intent citations: every action a reference permits must be justified by a quote from the intent. No LLM.

reference.md carries a section

    ## Intent citations
    - `<action id>`: "<quote>" · "<another quote>"

that runs to the next `## ` heading. Each quote must be an exact, case-sensitive substring of intent.md.
Permitted actions come from the action scopes of the reference's permits, read from Cedar's JSON form
(`==` and `in [...]`; forbids are ignored). A permit with no action constraint permits every action and
is always a problem. This is a check on the written derivation, not on behaviour.
"""

from __future__ import annotations

import re
from pathlib import Path

from pgi.analysis.provenance import _policy_json

SECTION = "## Intent citations"
_LINE = re.compile(r"^\s*-\s*`([^`]+)`\s*:\s*(.+?)\s*$")
_QUOTE = re.compile(r'"([^"]+)"')


def permitted_actions(reference: Path) -> set[str]:
    """Action ids named by permit scopes; "*" if some permit leaves the action unconstrained."""
    out: set[str] = set()
    for pol in _policy_json(Path(reference)).get("staticPolicies", {}).values():
        if pol["effect"] != "permit":
            continue
        scope = pol["action"]
        if scope["op"] == "All":
            out.add("*")
        for e in [scope.get("entity"), *(scope.get("entities") or [])]:
            if e:
                out.add(e["id"])
    return out


def parse_citations(md: str) -> dict[str, list[str]] | None:
    """{action: [quotes]} from the citations section, or None if the section is missing."""
    lines = md.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == SECTION)
    except StopIteration:
        return None
    out: dict[str, list[str]] = {}
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        m = _LINE.match(line)
        if m:
            out.setdefault(m.group(1), []).extend(_QUOTE.findall(m.group(2)))
    return out


def check(reference: Path, reference_md: Path, intent: Path) -> list[str]:
    """Problems, one string each; empty means every permitted action is cited from the intent."""
    cites = parse_citations(Path(reference_md).read_text())
    if cites is None:
        return [f"reference.md has no '{SECTION}' section"]
    text = Path(intent).read_text()
    actions = permitted_actions(reference)
    problems = []
    if "*" in actions:
        problems.append("a permit leaves the action unconstrained (permits every action)")
    for action in sorted(actions - {"*"}):
        if not cites.get(action):
            problems.append(f"{action}: permitted but has no intent quote")
        for q in cites.get(action, []):
            if q not in text:
                problems.append(f'{action}: quote not in intent.md: "{q}"')
    for action in sorted(set(cites) - actions):
        problems.append(f"{action}: cited but not permitted by the reference")
    return problems
