"""Naive generator: deterministic prompt, intent last, cache breakpoint on the static prefix, no retries."""

import json
from pathlib import Path

import pytest

from pgi.generators.inputs import load_scenario_inputs, strip_descriptions
from pgi.generators.naive import NaiveConfig, build_request, extract_policy, generate
from pgi.llm.cache import CachedLLM

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
S01 = DOMAIN / "scenarios" / "s01_close_after_approval"
S02 = DOMAIN / "scenarios" / "s02_site_scoped_reads"


class ScriptedProvider:
    """Returns canned texts in order and counts calls."""

    name = "scripted"

    def __init__(self, *texts):
        self.texts, self.calls, self.seen = list(texts), 0, []

    def call(self, model, messages, temperature, params):
        self.calls += 1
        self.seen.append({"model": model, "messages": messages, "temperature": temperature, "params": params})
        return {"model": model, "content": [{"type": "text", "text": self.texts.pop(0)}], "usage": {}}

    def text(self, raw):
        return raw["content"][0]["text"]

    def model_version(self, raw):
        return raw["model"]

    def usage(self, raw):
        return raw["usage"]


def test_inputs_are_what_scenario_yaml_names():
    inp = load_scenario_inputs(S02)
    assert inp.servers == ("wo", "iot")
    assert inp.schema_path.name == "wo_iot.cedarschema"
    assert inp.intent == (S02 / "intent.md").read_text()
    assert set(inp.hashes) >= {"schema", "intent", "reference", "universe", "manifest:wo", "manifest:iot"}


def test_request_layout_static_prefix_then_intent_last():
    inp = load_scenario_inputs(S01)
    messages, params = build_request(inp, NaiveConfig(model="m"))
    system = params["system"]
    assert [b.get("cache_control") for b in system][:-1] == [None] * (len(system) - 1)
    assert system[-1]["cache_control"] == {"type": "ephemeral"}  # one breakpoint, on the last static block
    static = "".join(b["text"] for b in system)
    assert inp.schema_text in static
    assert (DOMAIN / "manifests" / "wo.tools.json").read_text() in static  # raw pinned bytes when descriptions on
    assert inp.intent not in static
    assert len(messages) == 1 and messages[0]["role"] == "user"
    assert messages[0]["content"].startswith(inp.intent) and messages[0]["content"].endswith("Output only Cedar policies.")
    assert params["thinking"] == {"type": "adaptive"} and params["output_config"] == {"effort": "high"}
    assert "temperature" not in params


def test_request_is_deterministic():
    inp = load_scenario_inputs(S02)
    assert build_request(inp, NaiveConfig(model="m")) == build_request(load_scenario_inputs(S02), NaiveConfig(model="m"))


def test_strip_descriptions_keeps_a_parameter_named_description():
    wo = json.loads((DOMAIN / "manifests" / "wo.tools.json").read_text())
    stripped = strip_descriptions(wo)
    gen = next(t for t in stripped["tools"] if t["name"] == "generate_work_order")
    assert "description" not in gen                                  # tool description removed
    assert "description" in gen["inputSchema"]["properties"]          # the *parameter* survives
    assert "description" in gen["inputSchema"]["required"]
    assert '"description": "' not in json.dumps(stripped)             # no annotation text left anywhere
    assert wo == json.loads((DOMAIN / "manifests" / "wo.tools.json").read_text())  # input not mutated


def test_include_descriptions_off_changes_only_the_manifest_block():
    inp = load_scenario_inputs(S01)
    on = build_request(inp, NaiveConfig(model="m"))[1]["system"]
    off = build_request(inp, NaiveConfig(model="m", include_descriptions=False))[1]["system"]
    assert on[:-1] == off[:-1] and on[-1] != off[-1]
    assert "Close a work order" in on[-1]["text"] and "Close a work order" not in off[-1]["text"]


@pytest.mark.parametrize("text,policy,method", [
    ("permit (principal, action, resource);", "permit (principal, action, resource);", "raw"),
    ("Here you go:\n```cedar\npermit (principal, action, resource);\n```\nDone.", "permit (principal, action, resource);", "fenced"),
    ("```\nA;\n```\ntext\n```cedar\nB;\n```", "A;\n\nB;", "fenced"),
    ("", "", "raw"),
])
def test_extract_policy(text, policy, method):
    assert extract_policy(text) == (policy, method)


def test_invalid_output_is_returned_once_never_retried(tmp_path):
    provider = ScriptedProvider("I cannot write that policy.", "permit (principal, action, resource);")
    sample = generate(CachedLLM(provider, tmp_path), load_scenario_inputs(S01), NaiveConfig(model="m"), sample_index=0)
    assert provider.calls == 1
    assert sample.policy_text == "I cannot write that policy." and sample.extraction == "raw"
    assert provider.seen[0]["temperature"] is None
