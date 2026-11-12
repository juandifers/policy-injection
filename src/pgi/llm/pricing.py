"""USD prices per million tokens, from https://platform.claude.com/docs/en/about-claude/pricing (fetched 2026-11-12).

Costs are computed from the `usage` fields the API returns, never from estimates.
Haiku 5.5 is priced by prompt length (all input incl. cache reads/writes); only the <=100k tier is listed,
and `cost` refuses prompts above it rather than guess.
"""

from __future__ import annotations

PRICES = {  # input, 5m cache write, cache read, output
    "claude-sonnet-5-5": {"input": 2.00, "cache_write_5m": 2.50, "cache_read": 0.10, "output": 10.00},
    "claude-haiku-5-5": {"input": 0.10, "cache_write_5m": 0.125, "cache_read": 0.01, "output": 0.50, "max_prompt": 100_000},
}
BATCH_DISCOUNT = 0.5  # stacks with prompt caching


def cost(model: str, usage: dict, batch: bool = False) -> float:
    """USD cost of one call from its usage fields."""
    if model not in PRICES:
        raise KeyError(f"no recorded price for {model}")
    p = PRICES[model]
    inp = usage.get("input_tokens", 0) or 0
    write = usage.get("cache_creation_input_tokens", 0) or 0
    read = usage.get("cache_read_input_tokens", 0) or 0
    out = usage.get("output_tokens", 0) or 0
    if "max_prompt" in p and inp + write + read > p["max_prompt"]:
        raise ValueError(f"{model} prompt of {inp + write + read} tokens exceeds the priced tier ({p['max_prompt']})")
    usd = (inp * p["input"] + write * p["cache_write_5m"] + read * p["cache_read"] + out * p["output"]) / 1e6
    return usd * (BATCH_DISCOUNT if batch else 1.0)
