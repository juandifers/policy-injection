"""Retry-on-expiry around "run one sample", shared by the temporal runner and the Phase 3 instance runner (2026-11-22).

A sample whose provider call hits the wall-clock deadline (pgi.llm.deadline.CallDeadlineExceeded) is attempted again with the
same request, up to `max_retries` more times (default 2). The request is identical, so the cache key is identical and the
successful attempt is the one cache entry for that sample index; the abandoned calls are never cached. After the last expiry
the run stops with DeadlineRunStopped (the run folder stays as `.tmp-…` with FAILED; a rerun with the same arguments replays
every finished sample from the cache). A sample that succeeded after one or two expiries is a normal sample. Any other error
passes through untouched: failing loudly is still the rule.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from pgi.llm.deadline import CallDeadlineExceeded

T = TypeVar("T")
DEFAULT_MAX_RETRIES = 2


class DeadlineRunStopped(RuntimeError):
    """Every attempt on one sample expired; the run stops. `events`: the expiry events of that sample, in order."""

    def __init__(self, generator: str, sample: int, events: list[dict]) -> None:
        self.generator, self.sample, self.events = generator, sample, list(events)
        super().__init__(f"{generator} sample {sample}: {len(events)} attempts expired at the {events[-1]['deadline_s']:g} s deadline; "
                         "stopping the run (finished samples are in the LLM cache; rerun with the same arguments to resume)")


def run_sample_with_retries(fn: Callable[[int], T], *, generator: str, sample: int, max_retries: int = DEFAULT_MAX_RETRIES) -> tuple[T, list[dict]]:
    """Call `fn(attempt)` (one whole sample; attempt is 1-based, so attempt - 1 = expiries before it) until it returns or
    `max_retries` + 1 attempts expired. Returns (result, expiry events); each event is the DeadlineProvider's dict tagged with
    generator, sample and attempt."""
    events: list[dict] = []
    for attempt in range(1, max_retries + 2):
        try:
            return fn(attempt), events
        except CallDeadlineExceeded as e:
            e.event.update({"generator": generator, "sample": sample, "attempt": attempt})
            events.append(e.event)
            if attempt > max_retries:
                raise DeadlineRunStopped(generator, sample, events) from e
    raise AssertionError("unreachable")
