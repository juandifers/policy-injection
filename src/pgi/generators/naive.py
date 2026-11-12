"""Naive generator: one LLM call per sample, no critic, no retries.

Prompt = instructions + final Cedar schema + raw MCP manifests (static, cached prefix) + intent + "Output only
Cedar policies." (user turn, last). The output is extracted, never repaired; validity is measured downstream.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from pgi.generators.inputs import ScenarioInputs, strip_descriptions
from pgi.llm.cache import CachedLLM, Completion

INSTRUCTIONS = (
    "You write Cedar authorization policies for an AI agent that calls MCP tools.\n"
    "Below are the Cedar schema the policies must validate against and the MCP tool manifests "
    "(tools/list responses) of the servers the agent can call.\n"
    "The user message is the administrator's intent."
)
FINAL_LINE = "Output only Cedar policies."
_FENCE = re.compile(r"```[A-Za-z0-9_-]*\n(.*?)```", re.DOTALL)


@dataclass(frozen=True)
class NaiveConfig:
    """Every knob of the naive generator; recorded verbatim in each run's config."""

    model: str
    include_descriptions: bool = True  # Step 4 probe knob: manifest descriptions shown to the generator
    effort: str = "high"
    max_tokens: int = 16000
    generator: str = "naive"

    def as_dict(self) -> dict:
        """JSON-ready form."""
        return asdict(self)


def manifest_text(path: Path, include_descriptions: bool) -> str:
    """The manifest as shown to the generator: the pinned bytes, or a description-stripped copy."""
    if include_descriptions:
        return Path(path).read_text()
    return json.dumps(strip_descriptions(json.loads(Path(path).read_text())), indent=2, sort_keys=True) + "\n"


def static_blocks(inputs: ScenarioInputs, include_descriptions: bool) -> list[dict]:
    """System blocks shared by every sample of a scenario; the last carries the cache breakpoint."""
    manifests = "\n".join(f"### MCP server `{s}`\n```json\n{manifest_text(p, include_descriptions)}```\n"
                          for s, p in zip(inputs.servers, inputs.manifest_paths))
    blocks = [
        {"type": "text", "text": INSTRUCTIONS},
        {"type": "text", "text": f"## Cedar schema\n```cedarschema\n{inputs.schema_text}```\n"},
        {"type": "text", "text": f"## MCP tool manifests\n{manifests}"},
    ]
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def build_request(inputs: ScenarioInputs, config: NaiveConfig) -> tuple[list[dict], dict]:
    """The exact (messages, params) sent for one sample. No sampling parameters: API default."""
    messages = [{"role": "user", "content": f"{inputs.intent.rstrip()}\n\n{FINAL_LINE}"}]
    params = {"system": static_blocks(inputs, config.include_descriptions), "max_tokens": config.max_tokens,
              "thinking": {"type": "adaptive"}, "output_config": {"effort": config.effort}}
    return messages, params


def extract_policy(text: str) -> tuple[str, str]:
    """Policy text from a model response: the fenced blocks joined, or the whole text. Never repaired."""
    blocks = [b.strip() for b in _FENCE.findall(text)]
    if blocks:
        return "\n\n".join(blocks), "fenced"
    return text.strip(), "raw"


@dataclass(frozen=True)
class Sample:
    """One generated sample: the response and the extracted policy text (unvalidated)."""

    sample_index: int
    completion: Completion
    policy_text: str
    extraction: str


def generate(llm: CachedLLM, inputs: ScenarioInputs, config: NaiveConfig, sample_index: int) -> Sample:
    """One sample: one cached LLM call, then extraction. Invalid output is returned as-is, not retried."""
    messages, params = build_request(inputs, config)
    completion = llm.complete(config.model, messages, temperature=None, sample_index=sample_index, **params)
    policy, method = extract_policy(completion.text)
    return Sample(sample_index, completion, policy, method)
