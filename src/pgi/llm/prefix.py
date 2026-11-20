"""Identity of a request's cacheable prefix (Phase 3 prompt-cache telemetry).

The Anthropic prompt cache matches a byte-identical prefix (tools, then system, then messages) up to and including the
block that carries `cache_control`; entries are written only at that breakpoint. The thinking configuration and the
effort setting are rendered into the prompt, so changing them invalidates the entry
(https://platform.claude.com/docs/en/build-with-claude/prompt-caching, read 2026-11-20). The prefix hash here covers
exactly that: the model, the system blocks up to and including the last breakpoint, `thinking` and `output_config`. Our
requests carry no tools and put the breakpoint in `system`, so messages never enter the prefix. `max_tokens` is not part
of the prompt and is excluded.
"""

from __future__ import annotations

import hashlib
import json


def prefix_blocks(params: dict) -> list[dict]:
    """The system blocks up to and including the last one carrying `cache_control`. Raises ValueError if none does."""
    system = params.get("system") or []
    marked = [i for i, b in enumerate(system) if "cache_control" in b]
    if not marked:
        raise ValueError("no system block carries cache_control: the request has no cacheable prefix")
    return list(system[: marked[-1] + 1])


def prefix_hash(model: str, params: dict, strict: bool = True) -> str | None:
    """SHA-256 of the canonical JSON of (model, prefix blocks, thinking, output_config). `strict=False` returns None for a
    request without a breakpoint instead of raising."""
    try:
        blocks = prefix_blocks(params)
    except ValueError:
        if strict:
            raise
        return None
    key = {"model": model, "system_prefix": blocks, "thinking": params.get("thinking"), "output_config": params.get("output_config")}
    return hashlib.sha256(json.dumps(key, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
