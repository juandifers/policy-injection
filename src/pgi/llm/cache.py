"""On-disk LLM cache: the only path from a generator to an LLM API.

Key = model id + full messages + temperature + sample index + every other request parameter,
serialised as canonical JSON and hashed with SHA-256. Each response is stored as one JSON file
holding the key, the raw provider response and the model version string the API returned.
A hit never calls the API; an unreadable entry raises instead of silently re-calling.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


class CacheMiss(RuntimeError):
    """A request was not in the cache and API calls are disabled."""


class Provider(Protocol):
    """Adapter for one LLM API. `call` is the only method that touches the network."""

    name: str

    def call(self, model: str, messages: list[dict], temperature: float, params: dict) -> dict: ...
    def text(self, raw: dict) -> str: ...
    def model_version(self, raw: dict) -> str: ...
    def usage(self, raw: dict) -> dict: ...


@dataclass(frozen=True)
class Completion:
    """One cached or fresh response."""

    text: str
    model_version: str
    usage: dict
    key_hash: str
    cache_hit: bool
    raw: dict


def cache_key(model: str, messages: list[dict], temperature: float, sample_index: int, params: dict) -> dict:
    """The full cache key as a JSON-ready dict."""
    return {"model": model, "messages": messages, "temperature": temperature,
            "sample_index": sample_index, "params": params}


def key_hash(key: dict) -> str:
    """SHA-256 of the canonical JSON encoding of a key."""
    canonical = json.dumps(key, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


class CachedLLM:
    """Wraps a Provider so that every request is served from, or recorded into, the cache."""

    def __init__(self, provider: Provider, cache_dir: Path, allow_api: bool = True) -> None:
        self.provider, self.cache_dir, self.allow_api = provider, Path(cache_dir), allow_api
        self.api_calls = 0

    def _path(self, h: str) -> Path:
        """Where the entry for one key hash lives."""
        return self.cache_dir / h[:2] / f"{h}.json"

    def complete(self, model: str, messages: list[dict], *, temperature: float, sample_index: int,
                 **params: Any) -> Completion:
        """Return the cached response for this exact request, calling the API only on a miss."""
        key = cache_key(model, messages, temperature, sample_index, params)
        h = key_hash(key)
        path = self._path(h)
        if path.exists():
            entry = json.loads(path.read_text())  # corrupt entry -> ValueError, never a re-call
            if entry.get("key") != key:
                raise ValueError(f"cache entry {path} does not match its key")
            return Completion(entry["text"], entry["model_version"], entry["usage"], h, True, entry["raw"])
        if not self.allow_api:
            raise CacheMiss(f"no cache entry for {model} sample {sample_index} ({h[:12]}) and API calls are disabled")
        raw = self.provider.call(model, messages, temperature, params)
        self.api_calls += 1
        entry = {"key": key, "key_hash": h, "provider": self.provider.name,
                 "model_version": self.provider.model_version(raw), "usage": self.provider.usage(raw),
                 "text": self.provider.text(raw), "raw": raw,
                 "created_at": datetime.now(timezone.utc).isoformat()}
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp") as f:
            json.dump(entry, f, indent=1, ensure_ascii=False)
        os.replace(f.name, path)  # atomic: a crash never leaves a half-written entry
        return Completion(entry["text"], entry["model_version"], entry["usage"], h, False, raw)
