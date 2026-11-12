"""Enumeration backend: evaluates policies on a listed universe of requests with cedarpy.

Results are exact counts, but only over the listed requests. An empty surplus means
"no witness in this universe", not "the policy is safe".
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cedarpy
import yaml

Request = dict[str, Any]

_UNIVERSE_KEYS = {"principal", "resource", "entities", "cases", "refs"}
_CASE_KEYS = {"id", "principal", "action", "resource", "context"}


class OracleError(Exception):
    """Any validation or authorization error. Never interpreted as a deny."""


@dataclass(frozen=True)
class Universe:
    """A listed set of requests keyed by stable case id, plus the entity store they run against."""

    requests: dict[str, Request]
    entities: list[dict]
    defaults: dict[str, dict]

    @property
    def ids(self) -> frozenset[str]:
        """The case ids in this universe."""
        return frozenset(self.requests)

    def without(self, ids: Iterable[str]) -> Universe:
        """A copy of this universe with the given case ids removed."""
        drop = set(ids)
        if missing := drop - self.ids:
            raise OracleError(f"cannot remove unknown case ids: {sorted(missing)}")
        kept = {cid: req for cid, req in self.requests.items() if cid not in drop}
        return Universe(kept, self.entities, self.defaults)

    def with_case(self, case_id: str, case: dict) -> Universe:
        """A copy of this universe with one extra case, given in universe.yaml form."""
        if case_id in self.requests:
            raise OracleError(f"duplicate case id: {case_id!r}")
        return Universe({**self.requests, case_id: _build_request(case_id, case, self.defaults)},
                        self.entities, self.defaults)


def _build_request(case_id: str, case: dict, defaults: dict[str, dict]) -> Request:
    """Turn one universe.yaml case into a cedarpy request dict (without correlation id)."""
    if unknown := set(case) - _CASE_KEYS:
        raise OracleError(f"case {case_id!r}: unknown keys {sorted(unknown)}")
    req = {key: case.get(key, defaults.get(key)) for key in ("principal", "action", "resource")}
    if missing := [key for key, value in req.items() if value is None]:
        raise OracleError(f"case {case_id!r}: missing {missing}")
    req["context"] = case.get("context", {})
    return req


def load_universe(path: Path) -> Universe:
    """Load a universe.yaml file; reject unknown keys, missing fields and duplicate ids."""
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise OracleError(f"{path}: expected a mapping with a 'cases' list")
    if unknown := set(data) - _UNIVERSE_KEYS:
        raise OracleError(f"{path}: unknown top-level keys {sorted(unknown)}")
    defaults = {key: data[key] for key in ("principal", "resource") if key in data}
    requests: dict[str, Request] = {}
    for case in data["cases"]:
        case_id = case.get("id")
        if not isinstance(case_id, str) or not case_id:
            raise OracleError(f"{path}: every case needs a non-empty string id, got {case!r}")
        if case_id in requests:
            raise OracleError(f"{path}: duplicate case id {case_id!r}")
        requests[case_id] = _build_request(case_id, case, defaults)
    if not requests:
        raise OracleError(f"{path}: universe has no cases")
    return Universe(requests, data.get("entities") or [], defaults)


def validate(policy: Path, schema: Path) -> None:
    """Raise OracleError unless the policy file parses and validates against the schema."""
    result = cedarpy.validate_policies(Path(policy).read_text(), Path(schema).read_text())
    if not result.validation_passed:
        raise OracleError(f"{policy} fails validation: {[str(e) for e in result.errors]}")


def allowed(policy: Path, universe: Universe, schema: Path) -> set[str]:
    """allow-set(policy): the case ids in the universe that the policy allows."""
    validate(policy, schema)
    sent = [{**req, "correlation_id": cid} for cid, req in universe.requests.items()]
    results = cedarpy.is_authorized_batch(sent, Path(policy).read_text(), universe.entities,
                                          Path(schema).read_text())
    if len(results) != len(sent):
        raise OracleError(f"sent {len(sent)} requests, got {len(results)} results")
    # A request that fails to build comes back with no correlation id, so position is the only
    # way to name it in the error. Decisions themselves are matched by correlation id only.
    for req, res in zip(sent, results):
        if res.decision is cedarpy.Decision.NoDecision or res.diagnostics.errors:
            raise OracleError(f"case {req['correlation_id']!r} under {policy}: "
                              f"{res.decision.name} {res.diagnostics.errors}")
    by_id = {res.correlation_id: res for res in results}
    if len(by_id) != len(results) or set(by_id) != universe.ids:
        raise OracleError(f"correlation ids mismatch: sent {sorted(universe.ids)}, "
                          f"got {sorted(map(str, by_id))}")
    return {cid for cid, res in by_id.items() if res.allowed}


def surplus(policy: Path, reference: Path, universe: Universe, schema: Path) -> set[str]:
    """surplus(P, P_ref) = allow-set(P) − allow-set(P_ref). Is P wrong?"""
    return allowed(policy, universe, schema) - allowed(reference, universe, schema)


def expansion(adversarial: Path, clean_runs: Sequence[Path], universe: Universe, schema: Path) -> set[str]:
    """expansion(P_adv) = allow-set(P_adv) − ∪ allow-set(P_clean_i). Did the attack cause it?"""
    if not clean_runs:
        raise OracleError("expansion needs at least one clean run")
    envelope = set().union(*(allowed(p, universe, schema) for p in clean_runs))
    return allowed(adversarial, universe, schema) - envelope
