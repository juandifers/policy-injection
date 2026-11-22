"""Text-level tally of what a Dogwood policy's temporal predicates name: actions, event kinds, bound fields, literals.

This is TEXT, not behaviour: it complements the behavioural scores of pgi.runs.temporal_clean (which decide
over-permissive / over-strict / source accepted) by saying *why* a sample behaved as it did, e.g. "bound the authority
response but guessed the value `APPROVED`". Never used as a score. Whole-token regexes over the policy text; a policy
the regexes misread is reported as-is, so counts here are a lower bound.

    uv run --group dogwood python -m pgi.analysis.dogwood_text runs/<id>   # tally per generator
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

_PREDICATE = re.compile(r'([A-Za-z_][\w:]*)::Action::"([^"]+)"::(request|response|error)\s*\{(.*?)\}', re.DOTALL)
_BINDING = re.compile(r'([A-Za-z_][\w.]*)\s*:\s*([A-Za-z_][\w]*(?:::[A-Za-z_]\w*)+::"[^"]*"|"[^"]*"|true|false|-?\d+(?:\.\d+)?|context\.[\w.]+|principal|resource|_|[A-Za-z_]\w*)')
_ENTITY_LITERAL = re.compile(r'^[A-Za-z_][\w]*(?:::[A-Za-z_]\w*)+::"([^"]*)"$')
_STRING_LITERAL = re.compile(r'^"([^"]*)"$')
_COMMENT = re.compile(r"//[^\n]*")
_SCOPE_ACTION = re.compile(r'\b(permit|forbid)\s*\(\s*principal[^,]*,\s*action\s*==\s*[\w:]*Action::"([^"]+)"')


def predicate_tally(text: str) -> dict:
    """Temporal predicates (action, kind, {field: pattern}) and the actions each permit/forbid is scoped to."""
    clean = _COMMENT.sub("", text)
    predicates = []
    for ns, action, kind, body in _PREDICATE.findall(clean):
        fields = {f: v for f, v in _BINDING.findall(body)}
        predicates.append({"action": action, "kind": kind, "fields": fields})
    scoped = [(eff, a) for eff, a in _SCOPE_ACTION.findall(clean)]
    return {"predicates": predicates,
            "permit_actions": sorted({a for e, a in scoped if e == "permit"}),
            "forbid_actions": sorted({a for e, a in scoped if e == "forbid"}),
            "literals": sorted({v for p in predicates for v in p["fields"].values() if v.startswith('"')})}  # string literals only; see literal_id


def literal_id(pattern: str) -> str | None:
    """The quoted value of a literal pattern: `"X"` -> X, `Ns::Type::"X"` (enum entity) -> X; anything else -> None."""
    if m := _ENTITY_LITERAL.match(pattern):
        return m.group(1)
    if m := _STRING_LITERAL.match(pattern):
        return m.group(1)
    return None


def vocabulary_report(text: str, vocab: dict) -> dict:
    """Phase 2b evidence-vocabulary classification of one policy's temporal predicates (TEXT, never a score).

    vocab: authority_action, vendor_actions, contract_values, vendor_stated_values, approver_kind_fields (requirements.yaml
    `evidence_vocabulary`). Per predicate: role (authority / vendor / other) and each literal's classes (contract and/or
    vendor_stated, else neither). Policy-level: actions bound; `binding` (authority | vendor | both | authority+other |
    vendor+other | other | none); the literals of authority-bound predicates by class; `vendor_token_in_authority_predicate`
    (an authority literal that is vendor-stated and NOT a contract value: borrowed vocabulary); `invented_in_authority_predicate`
    (an authority literal in neither set); `approver_kind_present` (any predicate binds one of approver_kind_fields)."""
    contract, stated = set(vocab["contract_values"]), set(vocab["vendor_stated_values"])
    vendor_actions, approver_fields = set(vocab["vendor_actions"]), set(vocab["approver_kind_fields"])
    preds = []
    for p in predicate_tally(text)["predicates"]:
        role = "authority" if p["action"] == vocab["authority_action"] else "vendor" if p["action"] in vendor_actions else "other"
        lits = {}
        for f, v in p["fields"].items():
            if (lid := literal_id(v)) is not None:
                classes = [c for c, s in (("contract", contract), ("vendor_stated", stated)) if lid in s] or ["neither"]
                lits[f] = {"value": lid, "classes": classes}
        preds.append({"action": p["action"], "kind": p["kind"], "role": role, "literals": lits,
                      "approver_kind_bound": sorted(set(p["fields"]) & approver_fields)})
    roles = {p["role"] for p in preds}
    if not preds:
        binding = "none"
    elif {"authority", "vendor"} <= roles:
        binding = "both"
    elif roles == {"authority"}:
        binding = "authority"
    elif roles == {"vendor"}:
        binding = "vendor"
    elif "authority" in roles:
        binding = "authority+other"
    elif "vendor" in roles:
        binding = "vendor+other"
    else:
        binding = "other"
    auth = {"contract": set(), "vendor_stated": set(), "neither": set()}
    for p in preds:
        if p["role"] == "authority":
            for lit in p["literals"].values():
                for c in lit["classes"]:
                    auth[c].add(lit["value"])
    auth_sorted = {k: sorted(v) for k, v in auth.items()}
    return {"predicates": preds, "actions_bound": sorted({p["action"] for p in preds}), "binding": binding,
            "authority_literals": auth_sorted,
            "vendor_token_in_authority_predicate": bool(auth["vendor_stated"] - contract),
            "invented_in_authority_predicate": bool(auth["neither"]),
            "approver_kind_present": any(p["approver_kind_bound"] for p in preds)}


def tally_run(run: Path) -> dict:
    """Per generator: counts of predicate (action, kind), of output-field literals, of permitted/forbidden actions."""
    run = Path(run)
    out = {}
    for policy in sorted(run.glob("*/*/sample_*/policy.dw")):
        gen = policy.parents[1].name
        t = predicate_tally(policy.read_text())
        g = out.setdefault(gen, {"samples": 0, "predicate_action_kind": Counter(), "predicate_fields": Counter(),
                                 "literal_by_field": Counter(), "permit_actions": Counter(), "forbid_actions": Counter(),
                                 "predicates_per_sample": Counter()})
        g["samples"] += 1
        g["predicates_per_sample"][len(t["predicates"])] += 1
        for p in t["predicates"]:
            g["predicate_action_kind"][f'{p["action"]}::{p["kind"]}'] += 1
            for f, v in p["fields"].items():
                g["predicate_fields"][f] += 1
                if v.startswith('"'):
                    g["literal_by_field"][f"{f} = {v}"] += 1
        g["permit_actions"].update(t["permit_actions"])
        g["forbid_actions"].update(t["forbid_actions"])
    return {gen: {k: (dict(sorted(v.items(), key=lambda kv: (-kv[1], str(kv[0])))) if isinstance(v, Counter) else v)
                  for k, v in g.items()} for gen, g in out.items()}


if __name__ == "__main__":
    print(json.dumps(tally_run(Path(sys.argv[1])), indent=1))


# ---- Phase 2c: statements, action groups, and BIND / TOKEN scoped to the permits that can apply to a protected action
_EFFECT_OPEN = re.compile(r"\b(permit|forbid)\s*\(")
_ANNOT_ID = re.compile(r'@id\("([^"]*)"\)\s*$')
_ACTION_REF = r'[A-Za-z_][\w:]*::Action::"([^"]+)"'
_SCOPE_EQ = re.compile(rf"^action\s*==\s*{_ACTION_REF}$")
_SCOPE_LIST = re.compile(r"^action\s+in\s*\[(.*)\]$", re.DOTALL)
_SCOPE_GROUP = re.compile(rf"^action\s+in\s+{_ACTION_REF}$")
_CLAUSE_OPEN = re.compile(r"\s*(when\s+temporal|when|unless)\s*\{")
_GROUP_DECL = re.compile(r'\baction\s+"([^"]+)"\s+in\s+\[([^\]]*)\]')
_ACTION_DECL = re.compile(r'\baction\s+"([^"]+)"')
_OPEN, _CLOSE = {"(": ")", "{": "}", "[": "]"}, {")": "(", "}": "{", "]": "["}


def _skip_string(text: str, j: int) -> int:
    """j at an opening quote; return the index just past the closing quote."""
    j += 1
    while j < len(text) and text[j] != '"':
        j += 2 if text[j] == "\\" else 1
    return j + 1


def _balanced_end(text: str, i: int) -> int:
    """text[i] is an opening bracket; the index just past its matching close, or -1. Strings are skipped."""
    open_ch, close_ch, depth, j = text[i], _OPEN[text[i]], 0, i
    while j < len(text):
        c = text[j]
        if c == '"':
            j = _skip_string(text, j)
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return -1


def _split_top(text: str, sep: str) -> list[str]:
    """Split on `sep` at bracket depth 0, outside strings."""
    parts, depth, j, start = [], 0, 0, 0
    while j < len(text):
        c = text[j]
        if c == '"':
            j = _skip_string(text, j)
            continue
        if c in _OPEN:
            depth += 1
        elif c in _CLOSE:
            depth -= 1
        elif depth == 0 and text.startswith(sep, j):
            parts.append(text[start:j])
            j += len(sep)
            start = j
            continue
        j += 1
    parts.append(text[start:])
    return parts


def _action_scope(part: str) -> dict:
    """The action constraint of a scope: any | eq | in_list | in_group | unknown, with the action names it names."""
    s = re.sub(r"\s+", " ", part).strip()
    if s == "action":
        return {"kind": "any", "actions": []}
    if m := _SCOPE_EQ.match(s):
        return {"kind": "eq", "actions": [m.group(1)]}
    if m := _SCOPE_LIST.match(s):
        return {"kind": "in_list", "actions": re.findall(_ACTION_REF, m.group(1))}
    if m := _SCOPE_GROUP.match(s):
        return {"kind": "in_group", "actions": [m.group(1)]}
    return {"kind": "unknown", "actions": [], "text": s[:120]}


def statements(text: str) -> list[dict]:
    """Top-level permit/forbid statements of a Dogwood policy text (comments removed): effect, @id, action scope, Cedar
    `when`/`unless` clauses and `when temporal` block bodies. Malformed text yields what could be read; never raises."""
    clean = _COMMENT.sub("", text)
    out, pos = [], 0
    while m := _EFFECT_OPEN.search(clean, pos):
        lp = m.end() - 1
        end_scope = _balanced_end(clean, lp)
        if end_scope < 0:
            break
        parts = _split_top(clean[lp + 1:end_scope - 1], ",")
        scope = _action_scope(parts[1] if len(parts) >= 2 else "")
        cedar, blocks, p = [], [], end_scope
        while True:
            cm = _CLAUSE_OPEN.match(clean, p)
            if not cm:
                break
            brace = cm.end() - 1
            cend = _balanced_end(clean, brace)
            if cend < 0:
                break
            kw = re.sub(r"\s+", " ", cm.group(1))
            (blocks if kw == "when temporal" else cedar).append(clean[brace + 1:cend - 1] if kw == "when temporal" else {"kind": kw, "body": clean[brace + 1:cend - 1]})
            p = cend
        idm = _ANNOT_ID.search(clean, 0, m.start())
        out.append({"effect": m.group(1), "id": idm.group(1) if idm else None, "scope": scope,
                    "cedar_conditions": cedar, "temporal_blocks": blocks, "raw": clean[m.start():p]})
        pos = max(p, m.end())
    return out


def action_groups(schema_text: str) -> dict[str, set[str]]:
    """Declared action -> the transitive set of action groups containing it (`action "x" in [Ns::Action::"G", ...]`)."""
    parents = {name: set(re.findall(r'Action::"([^"]+)"', inside)) for name, inside in _GROUP_DECL.findall(schema_text)}
    out = {}
    for a in set(_ACTION_DECL.findall(schema_text)):
        seen, stack = set(), list(parents.get(a, ()))
        while stack:
            g = stack.pop()
            if g not in seen:
                seen.add(g)
                stack += parents.get(g, ())
        out[a] = seen
    return out


def applies_to(scope: dict, action: str, groups: dict[str, set[str]] | None) -> tuple[bool, bool]:
    """(may this scope apply to `action`?, could that be resolved?). Unresolvable scopes (unknown form, or a group the
    schema does not declare, or no schema) are reported as applying, with resolved=False, so callers can fail closed."""
    kind = scope["kind"]
    if kind == "any":
        return True, True
    if kind in ("eq", "in_list"):
        return action in scope["actions"], True
    if kind == "in_group" and groups is not None:
        (g,) = scope["actions"]
        known = set(groups) | set().union(*groups.values()) if groups else set()
        if g in known:
            return g in groups.get(action, set()), True
    return True, False


def _block_predicates(body: str) -> list[dict]:
    return [{"action": a, "kind": k, "fields": {f: v for f, v in _BINDING.findall(b)}} for _, a, k, b in _PREDICATE.findall(body)]


def close_binding_report(text: str, vocab: dict, protected_action: str, schema_text: str | None = None) -> dict:
    """Phase 2c BIND / TOKEN for one policy text (TEXT, never a score; runs on invalid text too).

    BIND: the evidence roles (authority / vendor, from `vocab`) of the temporal predicates in every PERMIT that can apply to
    `protected_action` (scope `action == it`, a list containing it, a schema-declared group containing it, or unconstrained):
    authority | vendor | both | none; other tools bound there are listed separately. TOKEN: a vendor-stated value that is not
    a contract value appears in a predicate over the authority tool anywhere in the policy (policy-wide, forbids included);
    `token_in_close_permits` restricts it to the permits BIND looked at. `unresolved_scope` flags a permit whose scope could
    not be resolved (counted as applying)."""
    groups = action_groups(schema_text) if schema_text is not None else None
    contract, stated, vendor_actions = set(vocab["contract_values"]), set(vocab["vendor_stated_values"]), set(vocab["vendor_actions"])
    role = lambda a: "authority" if a == vocab["authority_action"] else "vendor" if a in vendor_actions else "other"
    sts = statements(text)
    considered, unresolved = [], False
    for s in sts:
        if s["effect"] != "permit":
            continue
        ap, resolved = applies_to(s["scope"], protected_action, groups)
        unresolved |= not resolved
        if ap:
            considered.append(s)
    close_preds = [p for s in considered for b in s["temporal_blocks"] for p in _block_predicates(b)]
    all_preds = [p for s in sts for b in s["temporal_blocks"] for p in _block_predicates(b)]
    roles = {role(p["action"]) for p in close_preds}
    bind = "both" if {"authority", "vendor"} <= roles else "authority" if "authority" in roles else "vendor" if "vendor" in roles else "none"

    def tokens(preds):
        return sorted({lid for p in preds if role(p["action"]) == "authority" for v in p["fields"].values()
                       if (lid := literal_id(v)) is not None and lid in stated and lid not in contract})
    permit_roles = [{"id": s["id"], "roles": sorted({role(p["action"]) for b in s["temporal_blocks"] for p in _block_predicates(b)}),
                     "alternatives": any(len(_split_top(b, "||")) > 1 for b in s["temporal_blocks"])} for s in considered]
    return {"bind": bind, "other_actions_bound": sorted({p["action"] for p in close_preds if role(p["action"]) == "other"}),
            "token": bool(tokens(all_preds)), "authority_tokens": tokens(all_preds), "token_in_close_permits": bool(tokens(close_preds)),
            "permits_considered": len(considered), "unresolved_scope": unresolved,
            "predicates": [{"action": p["action"], "kind": p["kind"], "role": role(p["action"])} for p in close_preds],
            "permit_roles": permit_roles, "form": binding_form(permit_roles)}


FORMS = ("designated_only", "mirror_only", "either_source", "both_required", "other_tool", "none", "mixed")


def binding_form(permit_roles: list[dict]) -> str:
    """Phase 3 E1 binding form (TEXT, descriptive only) from the per-permit role sets of the permits that can apply to the
    protected action ("authority" = the designated source, "vendor" = the mirror):
    - none: no such permit, or none of them carries a temporal predicate;
    - designated_only / mirror_only / other_tool: every permit binds only that role;
    - either_source: separate permits, some binding only the designated source and some only the mirror, nothing else; or one
      permit whose block offers the two as `||` alternatives (not valid Dogwood, but it is what the text says);
    - both_required: exactly one permit, binding the designated source and the mirror in one conjoined block, no alternatives;
    - mixed: any other combination (e.g. an unconditional permit next to a bound one, or two both-required permits)."""
    if not permit_roles or all(not p["roles"] for p in permit_roles):
        return "none"
    if any(not p["roles"] for p in permit_roles):
        return "mixed"
    sets = [frozenset(p["roles"]) for p in permit_roles]
    alt = any(p["alternatives"] for p in permit_roles)
    for name, role_ in (("designated_only", "authority"), ("mirror_only", "vendor"), ("other_tool", "other")):
        if all(s == {role_} for s in sets) and not alt:
            return name
    both = frozenset({"authority", "vendor"})
    if len(sets) == 1 and sets[0] == both:
        return "either_source" if alt else "both_required"
    if not alt and all(s in ({"authority"}, {"vendor"}) for s in sets) and {"authority"} in [set(s) for s in sets] and {"vendor"} in [set(s) for s in sets]:
        return "either_source"
    return "mixed"
