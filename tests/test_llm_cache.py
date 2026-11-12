"""The on-disk LLM cache: the only path to an LLM. A finished run must replay with zero API calls."""

import itertools
import json

import pytest

from pgi.llm.cache import CacheMiss, CachedLLM, Completion


class FakeProvider:
    """Stands in for a real API: counts calls and returns a different text every time."""

    name = "fake"

    def __init__(self):
        self.calls = 0
        self._n = itertools.count()

    def call(self, model, messages, temperature, params):
        self.calls += 1
        n = next(self._n)
        return {"model": f"{model}-2026-11-01", "content": f"permit /* sample {n} */",
                "usage": {"input_tokens": 10, "output_tokens": 5}}

    def text(self, raw):
        return raw["content"]

    def model_version(self, raw):
        return raw["model"]

    def usage(self, raw):
        return raw["usage"]


PROMPT = [{"role": "user", "content": "write a policy"}]


def run(llm, n=3, temperature=1.0):
    """A miniature 'run': n samples of one prompt."""
    return [llm.complete("m-1", PROMPT, temperature=temperature, sample_index=i, max_tokens=100).text
            for i in range(n)]


def test_rerun_makes_zero_api_calls_and_reproduces_outputs(tmp_path):
    first_provider = FakeProvider()
    first = run(CachedLLM(first_provider, tmp_path))
    assert first_provider.calls == 3
    assert len(set(first)) == 3  # distinct samples, as at temperature > 0

    replay_provider = FakeProvider()
    replay = run(CachedLLM(replay_provider, tmp_path))
    assert replay_provider.calls == 0
    assert replay == first


def test_offline_mode_replays_and_refuses_to_call(tmp_path):
    run(CachedLLM(FakeProvider(), tmp_path))
    offline = CachedLLM(FakeProvider(), tmp_path, allow_api=False)
    assert len(run(offline)) == 3
    with pytest.raises(CacheMiss):
        offline.complete("m-1", PROMPT, temperature=1.0, sample_index=99, max_tokens=100)


@pytest.mark.parametrize("change", [
    {"model": "m-2"},
    {"messages": [{"role": "user", "content": "write a policy!"}]},
    {"temperature": 0.7},
    {"sample_index": 1},
    {"max_tokens": 200},
])
def test_every_key_component_matters(tmp_path, change):
    provider = FakeProvider()
    llm = CachedLLM(provider, tmp_path)
    base = dict(model="m-1", messages=PROMPT, temperature=1.0, sample_index=0, max_tokens=100)
    llm.complete(**base)
    llm.complete(**{**base, **change})
    assert provider.calls == 2


def test_entry_is_json_with_key_raw_response_and_model_version(tmp_path):
    c = CachedLLM(FakeProvider(), tmp_path).complete("m-1", PROMPT, temperature=1.0, sample_index=0, max_tokens=100)
    assert isinstance(c, Completion) and not c.cache_hit
    (entry_path,) = tmp_path.rglob("*.json")
    entry = json.loads(entry_path.read_text())
    assert entry["key"]["model"] == "m-1" and entry["key"]["sample_index"] == 0
    assert entry["key"]["messages"] == PROMPT
    assert entry["model_version"] == "m-1-2026-11-01" == c.model_version
    assert entry["raw"]["content"] == c.text
    hit = CachedLLM(FakeProvider(), tmp_path).complete("m-1", PROMPT, temperature=1.0, sample_index=0, max_tokens=100)
    assert hit.cache_hit and hit.text == c.text and hit.key_hash == c.key_hash


def test_corrupt_entry_raises_instead_of_calling(tmp_path):
    llm = CachedLLM(FakeProvider(), tmp_path)
    c = llm.complete("m-1", PROMPT, temperature=1.0, sample_index=0, max_tokens=100)
    (entry_path,) = tmp_path.rglob("*.json")
    entry_path.write_text("{not json")
    provider = FakeProvider()
    with pytest.raises(ValueError):
        CachedLLM(provider, tmp_path).complete("m-1", PROMPT, temperature=1.0, sample_index=0, max_tokens=100)
    assert provider.calls == 0
