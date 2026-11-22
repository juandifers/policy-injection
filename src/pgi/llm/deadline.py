"""A hard wall-clock deadline around every provider call, enforced outside the SDK (2026-11-22).

Three runs hung on a call that never returned (decisions 2026-11-17; findings, Phase 2c incident); on the last one neither the
SDK's 300 s request timeout nor its retries fired. `DeadlineProvider` wraps a Provider: the inner `call` runs in a daemon
thread and the caller waits at most `seconds`. On expiry it raises `CallDeadlineExceeded` and abandons the thread. Python cannot
stop that thread, so its socket leaks until the SDK gives up or the process exits; its result lands in a box nobody reads, which
is what makes "a late result is never returned and never cached" structural (CachedLLM writes only what `call` returns).

Best effort billing evidence: if the abandoned call does return before the process ends, its usage is written into the expiry
event (`late_usage`, `late_elapsed_s`), or its error into `late_error`. Events live on the wrapper (`expiries`) as dicts that
the runners embed in their records, so a late arrival shows up wherever the event has not been serialised yet.

Default 600 s: it must exceed the time a legitimate call needs to emit `max_tokens` (so the deadline never censors long
outputs) and it leaves room for one SDK timeout (300 s) plus a successful SDK retry.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from pgi.llm.prefix import prefix_hash

DEFAULT_DEADLINE_S = 600.0


class CallDeadlineExceeded(RuntimeError):
    """A provider call did not return within the wall-clock deadline; the call was abandoned (its result is discarded)."""

    def __init__(self, event: dict) -> None:
        self.event = event
        self.elapsed_s, self.deadline_s = event["elapsed_s"], event["deadline_s"]
        self.model, self.prefix_hash = event["model"], event["prefix_hash"]
        super().__init__(f"provider call on {self.model} did not return within {self.deadline_s:g} s (waited {self.elapsed_s:.1f} s, "
                         f"prefix {(self.prefix_hash or 'none')[:12]}); the call is abandoned and its result, if any, is discarded")


class DeadlineProvider:
    """Provider wrapper enforcing a wall-clock deadline on each `call` (module doc). `expiries`: one event dict per expiry."""

    def __init__(self, provider, seconds: float = DEFAULT_DEADLINE_S) -> None:
        if not seconds > 0:
            raise ValueError(f"deadline must be positive, got {seconds!r}")
        self.provider, self.seconds, self.name = provider, float(seconds), provider.name
        self.expiries: list[dict] = []

    def request_settings(self) -> dict:
        """The inner provider's transport settings plus the deadline."""
        inner = getattr(self.provider, "request_settings", None)
        return (inner() if inner is not None else {}) | {"deadline_s": self.seconds}

    def call(self, model: str, messages: list[dict], temperature: float | None, params: dict) -> dict:
        state: dict = {"done": False, "expired": False}
        lock = threading.Lock()
        start = time.monotonic()

        def work() -> None:
            try:
                result, error = self.provider.call(model, messages, temperature, params), None
            except BaseException as e:  # re-raised in the caller, or recorded in the event when late
                result, error = None, e
            with lock:
                state["done"] = True
                if not state["expired"]:
                    state["result"], state["error"] = result, error
                    return
                ev = state["event"]
                ev["late_elapsed_s"] = round(time.monotonic() - start, 3)
                ev["late_returned_at"] = datetime.now(timezone.utc).isoformat()
                if error is None:
                    try:
                        ev["late_usage"] = self.provider.usage(result)
                    except Exception as e:  # best effort only
                        ev["late_error"] = f"usage unreadable: {e!r}"
                else:
                    ev["late_error"] = repr(error)

        t = threading.Thread(target=work, name=f"pgi-call-{model}", daemon=True)
        t.start()
        t.join(self.seconds)
        with lock:
            if not state["done"]:
                state["expired"] = True
                event = {"kind": "deadline_expired", "at": datetime.now(timezone.utc).isoformat(), "model": model,
                         "deadline_s": self.seconds, "elapsed_s": round(time.monotonic() - start, 3),
                         "prefix_hash": prefix_hash(model, params, strict=False),
                         "late_usage": None, "late_elapsed_s": None, "late_returned_at": None, "late_error": None}
                state["event"] = event
                self.expiries.append(event)
                raise CallDeadlineExceeded(event)
        if state["error"] is not None:
            raise state["error"]
        return state["result"]

    def text(self, raw: dict) -> str:
        return self.provider.text(raw)

    def model_version(self, raw: dict) -> str:
        return self.provider.model_version(raw)

    def usage(self, raw: dict) -> dict:
        return self.provider.usage(raw)

    def cache_usage(self, raw: dict) -> dict | None:
        inner = getattr(self.provider, "cache_usage", None)
        return inner(raw) if inner is not None else None
