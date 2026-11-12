"""Anthropic Messages API adapter for pgi.llm.cache. The only module that calls the network.

Only CachedLLM should call `call`; generators never touch this class directly.
"""

from __future__ import annotations

import anthropic

from pgi.llm.env import load_env


class AnthropicProvider:
    """Sends one Messages API request and returns the raw response as a dict."""

    name = "anthropic"

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        if client is None:
            load_env()
            client = anthropic.Anthropic()
        self.client = client

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
