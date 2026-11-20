"""Resolver over trusted inputs only (Phase 3, E1): which target owns the approval evidence, whether every other source is
excluded, and which action is the evidence. Domain-agnostic; no LLM; never reads a manifest, a description or a cell label.

The resolver certifies REGISTERED templates; it does not interpret free text. Inputs: the intent text, the target prefixes
(with each target's tool names), a registry of sentences (decision 2026-11-20) and, optionally, the trusted catalogue of a D4
cell. Rules:
- Owner: the one target prefix, other than the fixed targets, that occurs in the intent as a whole word, case-sensitive
  (`\\b`, so `Name___tool` is not a mention of `Name`). Zero or two matches: no owner. Prefixes only, never tool names, so an
  echo-named mirror resolves exactly like a plain one.
- Exclusive is true only when one of these holds: the intent contains a registered exclusion sentence with the owner's name
  filled in (exact match); or it contains the registered action sentence (which names the owner's full action id); or a
  catalogue is present with exactly one evidence action.
- Evidence action is returned only when exclusive is true: the owner's single action, or the action the action sentence or
  the catalogue names. If those disagree, ResolverError.
Required results for the t02 levels: D0 nothing; D1 an owner without exclusion; D2, D3 and D4 exactly one action with exclusion.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass

PLACEHOLDER = "{AUTH}"
_ACTION_ID = re.compile(r"`([A-Za-z_][\w]*___[A-Za-z_]\w*)`")


class ResolverError(ValueError):
    """The registered inputs disagree (e.g. the catalogue names another action than the owner's)."""


@dataclass(frozen=True)
class Registry:
    """The registered sentences the resolver certifies. Each carries the `{AUTH}` placeholder exactly once; the action sentence
    also names the full action id in backticks. `source` records where the sentences came from (file path and hash)."""

    exclusion_sentences: tuple[str, ...]
    action_sentence: str
    source: str = ""

    def __post_init__(self) -> None:
        for s in (*self.exclusion_sentences, self.action_sentence):
            if s.count(PLACEHOLDER) != 1:
                raise ValueError(f"registered sentence must contain {PLACEHOLDER} exactly once: {s!r}")
        if not _ACTION_ID.search(self.action_sentence.replace(PLACEHOLDER, "X")):
            raise ValueError("the action sentence must name the full action id in backticks, e.g. `{AUTH}___get_approval`")

    def sha256(self) -> str:
        body = json.dumps({"exclusion_sentences": list(self.exclusion_sentences), "action_sentence": self.action_sentence},
                          sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(body.encode()).hexdigest()


@dataclass(frozen=True)
class Resolution:
    owner: str | None
    exclusive: bool
    evidence_action: str | None
    basis: tuple[str, ...]     # which rules fired: exclusion_sentence, action_sentence, contract_block

    def as_dict(self) -> dict:
        return asdict(self)


def mentions(intent: str, name: str) -> bool:
    """Whole-word, case-sensitive mention of a target prefix (underscores are word characters, so `Name___tool` is not one)."""
    return re.search(rf"\b{re.escape(name)}\b", intent) is not None


def owner_of(intent: str, targets: Mapping[str, Sequence[str]], fixed_targets: Sequence[str] = ()) -> str | None:
    """The unique non-fixed target prefix mentioned in the intent, or None."""
    found = [t for t in targets if t not in fixed_targets and mentions(intent, t)]
    return found[0] if len(found) == 1 else None


def _catalogue_action(catalogue: Mapping | None) -> str | None:
    """The catalogue's evidence action when it names exactly one, else None."""
    if not catalogue:
        return None
    ev = catalogue.get("evidence")
    if isinstance(ev, Mapping):
        a = ev.get("action")
        return a if isinstance(a, str) and a else None
    if isinstance(ev, Sequence) and not isinstance(ev, str) and len(ev) == 1 and isinstance(ev[0], Mapping):
        a = ev[0].get("action")
        return a if isinstance(a, str) and a else None
    return None


def resolve(intent: str, targets: Mapping[str, Sequence[str]], registry: Registry, *, fixed_targets: Sequence[str] = (),
            catalogue: Mapping | None = None) -> Resolution:
    """Owner, exclusivity and evidence action of one intent under the registry (module doc)."""
    owner = owner_of(intent, targets, fixed_targets)
    basis: list[str] = []
    named: set[str] = set()
    if owner is not None:
        if any(s.replace(PLACEHOLDER, owner) in intent for s in registry.exclusion_sentences):
            basis.append("exclusion_sentence")
        filled = registry.action_sentence.replace(PLACEHOLDER, owner)
        if filled in intent:
            basis.append("action_sentence")
            named.update(_ACTION_ID.findall(filled))
    cat_action = _catalogue_action(catalogue)
    if cat_action is not None:
        basis.append("contract_block")
        named.add(cat_action)
    exclusive = bool(basis)
    if not exclusive:
        return Resolution(owner, False, None, ())
    if owner is not None and len(targets[owner]) == 1:
        named.add(f"{owner}___{targets[owner][0]}")
    if len(named) != 1:
        raise ResolverError(f"exclusive intent but the registered inputs name {sorted(named) or 'no'} evidence action(s) "
                            f"(owner {owner!r}, basis {basis})")
    return Resolution(owner, True, next(iter(named)), tuple(basis))
