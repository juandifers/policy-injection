"""Re-score a finished run's stored policies against current inputs, into a new run folder. No LLM path at all."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from pgi.generators import critic, naive
from pgi.generators.inputs import load_scenario_inputs
from pgi.llm.cache import CachedLLM
from pgi.oracle import sym
from pgi.runs import clean
from pgi.runs.judge import score
from pgi.runs.rescore import rescore_into
from test_runs import Fake
from test_snapshot import S01, tmp_domain


@pytest.fixture(autouse=True, scope="module")
def _symcc():
    try:
        sym.check_available()
    except sym.SymccUnavailable as e:
        pytest.skip(str(e))


def _tree_hash(folder: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(folder)).encode() + p.read_bytes())
    return h.hexdigest()


@pytest.fixture
def source_run(tmp_path):
    """A finished run on s01 (Fake: weak_same_wo, surplus c3), one naive and one Sondera-style sample."""
    runs = tmp_path / "runs"
    llm = CachedLLM(Fake(), tmp_path / "cache")
    inp_live = load_scenario_inputs(S01)
    with clean.atomic_run_dir(runs, "src") as out:
        from pgi.runs.snapshot import snapshot
        inp = snapshot(inp_live, out / "inputs" / inp_live.name)
        clean._dump(out / "config.json", {"run_id": "src", "model": "claude-haiku-5-5", "n": 1,
                                          "generators_run": ["naive", "sondera"]})
        clean.run_naive(llm, inp, naive.NaiveConfig("claude-haiku-5-5"), 0, out / inp.name / "naive" / "sample_00")
        clean.run_sondera(llm, inp, critic.SonderaConfig("claude-haiku-5-5"), 0, out / inp.name / "sondera" / "sample_00")
    return runs / "src"


def test_rescore_into_uses_current_inputs_and_never_touches_the_source(tmp_path, source_run):
    scen = tmp_domain(tmp_path)
    shutil.copy(S01 / "weak_same_wo.cedar", scen / "reference.cedar")  # "new reference": c3 no longer surplus
    before = _tree_hash(source_run)
    out = rescore_into(source_run, [scen], tmp_path / "runs", "t")
    assert _tree_hash(source_run) == before
    assert out.parent == tmp_path / "runs" and out.name.endswith("-rescore-t")

    cfg = json.loads((out / "config.json").read_text())
    assert cfg["rescore_of"] == "src" and cfg["api_calls"] == 0
    assert cfg["scenarios"][S01.name]["hashes"] == load_scenario_inputs(scen).hashes

    for gen in ("naive", "sondera"):
        new, old = out / S01.name / gen / "sample_00", source_run / S01.name / gen / "sample_00"
        assert (new / "policy.cedar").read_bytes() == (old / "policy.cedar").read_bytes()
        rec = json.loads((new / "oracle.json").read_text())
        assert rec["enumeration"]["surplus"] == []                          # scored against the new reference
        assert json.loads((old / "oracle.json").read_text())["enumeration"]["surplus"] == ["c3"]
        live = score(new / "policy.cedar", load_scenario_inputs(scen))
        assert rec["enumeration"] == live["enumeration"]
        assert (new / "defaults.json").is_file() and (new / "provenance.json").is_file()
    sond = json.loads((out / S01.name / "sondera" / "sample_00" / "oracle.json").read_text())
    assert sond["critic"] == json.loads((source_run / S01.name / "sondera" / "sample_00" / "oracle.json").read_text())["critic"]
    assert (out / S01.name / "sondera" / "sample_00" / "round1.json").is_file()

    summary = json.loads((out / "summary.json").read_text())
    for s in summary.values():
        assert s["api_calls"] == 0 and s["cost_usd_this_run"] == 0
        assert s["calls"] > 0                                            # the source run's call records, kept
    assert (out / "summary.md").is_file()


def test_rescore_into_refuses_a_scenario_the_source_run_lacks(tmp_path, source_run):
    other = tmp_path / "elsewhere" / "s99_missing"
    other.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        rescore_into(source_run, [other], tmp_path / "runs", "t")
