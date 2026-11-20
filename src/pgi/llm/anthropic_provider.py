"""Anthropic Messages API adapter for pgi.llm.cache. The only module that calls the network.

Only CachedLLM should call `call`; generators never touch this class directly.
"""

from __future__ import annotations

import anthropic

from pgi.llm.env import load_env


DEFAULT_TIMEOUT_S = 300.0   # per request (SDK default is 600 s; a goal-level call hung past it on 2026-11-16, decisions 2026-11-17)
DEFAULT_MAX_RETRIES = 2     # the SDK's own bounded retry on connection errors / 408 / 409 / 429 / 5xx (its default)


class AnthropicProvider:
    """Sends one Messages API request and returns the raw response as a dict.

    Every request has an explicit timeout and a bounded retry count (recorded in run configs since 2026-11-18); a request
    that times out after the retries raises, so a run fails loudly instead of hanging.
    """

    name = "anthropic"

    def __init__(self, client: anthropic.Anthropic | None = None, timeout_s: float = DEFAULT_TIMEOUT_S,
                 max_retries: int = DEFAULT_MAX_RETRIES) -> None:
        if client is None:
            load_env()
            client = anthropic.Anthropic(timeout=timeout_s, max_retries=max_retries)
        self.client = client
        self.timeout_s, self.max_retries = timeout_s, max_retries

    def request_settings(self) -> dict:
        """What to record in a run config about transport: timeout and retry bound."""
        return {"timeout_s": self.timeout_s, "max_retries": self.max_retries}

    def call(self, model: str, messages: list[dict], temperature: float | None, params: dict) -> dict:
        """One non-streaming request. Sampling parameters are refused: SDK 2.x has none, and Sonnet 5.5 rejects them."""
        if temperature is not None:
            raise ValueError("temperature is not supported; pass None to use the API default")
        response = self.client.messages.create(model=model, messages=messages, **params)
        raw = response.to_dict()
        raw["_request_id"] = response._request_id
        return raw

    def text(self, raw: dict) -> str:
        """Concatenated text blocks; thinking blocks are excluded."""
        return "".join(b["text"] for b in raw.get("content", []) if b.get("type") == "text")

    def model_version(self, raw: dict) -> str:
        """The model id the API reports having served."""
        return raw["model"]

    def usage(self, raw: dict) -> dict:
        """Token usage exactly as returned."""
        return raw.get("usage", {})

    CACHE_FIELDS = ("cache_creation_input_tokens", "cache_read_input_tokens", "input_tokens", "output_tokens")

    def cache_usage(self, raw: dict) -> dict | None:
        """The four prompt-cache token counts (cache write, cache read, uncached input, output), or None when the response
        carries no cache fields (telemetry and the circuit breaker are then disabled)."""
        u = raw.get("usage") or {}
        if "cache_read_input_tokens" not in u or "cache_creation_input_tokens" not in u:
            return None
        return {k: int(u.get(k) or 0) for k in self.CACHE_FIELDS}
