"""Run folders carry their own inputs: re-scoring reads runs/<id>/inputs/, never the live scenario files."""

import json
import shutil
from pathlib import Path

import pytest

from pgi.generators.inputs import load_scenario_inputs
from pgi.oracle import sym
from pgi.runs.judge import score
from pgi.runs.rescore import rescore
from pgi.runs.snapshot import SnapshotError, load_snapshot, snapshot

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domains" / "assetopsbench"
S01 = DOMAIN / "scenarios" / "s01_close_after_approval"
SMOKE1 = ROOT / "runs" / "20261112T194818Z-clean-smoke"
SMOKE1_INPUTS = ROOT / "tests" / "fixtures" / "smoke1_inputs"  # restored from git faf37e6, hash-checked


@pytest.fixture(autouse=True, scope="module")
def _symcc():
    try:
        sym.check_available()
    except sym.SymccUnavailable as e:
        pytest.skip(str(e))


def behaviour(rec: dict) -> dict:
    """An oracle record minus the file paths it names (validation.policy / validation.schema): results only."""
    rec = json.loads(json.dumps(rec))
    rec.pop("critic", None)
    rec.pop("cause_tags", None)
    for k in ("policy", "schema"):
        rec["validation"].pop(k)
    return rec


def tmp_domain(tmp_path: Path) -> Path:
    """A copy of the AOB domain pieces s01 needs, so the test can change 'repo' files freely."""
    dom = tmp_path / "repo" / "domains" / "assetopsbench"
    shutil.copytree(DOMAIN / "schema", dom / "schema")
    shutil.copytree(DOMAIN / "manifests", dom / "manifests")
    shutil.copytree(S01, dom / "scenarios" / S01.name)
    return dom / "scenarios" / S01.name


def test_snapshot_copies_every_input_with_identical_hashes(tmp_path):
    inp = load_scenario_inputs(S01)
    snap = snapshot(inp, tmp_path / "inputs" / inp.name)
    assert snap.hashes == inp.hashes
    assert snap.folder == tmp_path / "inputs" / inp.name
    assert snap.schema_path.is_relative_to(snap.folder)
    assert all(p.is_relative_to(snap.folder) for p in snap.manifest_paths)
    assert snap.intent == inp.intent and snap.schema_text == inp.schema_text
    assert load_snapshot(snap.folder) == snap


def test_load_snapshot_fails_loudly_on_a_changed_file(tmp_path):
    snap = snapshot(load_scenario_inputs(S01), tmp_path / "inputs" / "s01")
    (snap.folder / "universe.yaml").write_text((snap.folder / "universe.yaml").read_text() + "\n# edited\n")
    with pytest.raises(SnapshotError, match="universe"):
        load_snapshot(snap.folder)


def test_rescore_is_unaffected_by_later_changes_to_the_scenario_files(tmp_path):
    scen = tmp_domain(tmp_path)
    run = tmp_path / "run"
    snap = snapshot(load_scenario_inputs(scen), run / "inputs" / scen.name)
    sample = run / scen.name / "naive" / "sample_00"
    sample.mkdir(parents=True)
    shutil.copy(S01 / "weak_same_wo.cedar", sample / "policy.cedar")
    before = rescore(run)
    assert before[f"{scen.name}/naive/sample_00"]["enumeration"]["surplus"] == ["c3"]

    # Change the "repo": drop c3 from the universe and weaken the reference to the candidate.
    lines = (scen / "universe.yaml").read_text().splitlines()
    i = next(k for k, l in enumerate(lines) if l.strip().startswith("- id: c3"))
    j = next(k for k in range(i + 1, len(lines)) if lines[k].strip().startswith("- id:"))
    (scen / "universe.yaml").write_text("\n".join(lines[:i] + lines[j:]) + "\n")
    shutil.copy(S01 / "weak_same_wo.cedar", scen / "reference.cedar")

    live = score(sample / "policy.cedar", load_scenario_inputs(scen))
    assert behaviour(live) != behaviour(before[f"{scen.name}/naive/sample_00"])  # the change matters live ...
    assert live["enumeration"]["surplus"] == []
    assert rescore(run) == before                                                # ... not from the snapshot
    assert load_snapshot(snap.folder) == snap


def test_smoke1_fixture_matches_the_hashes_the_run_recorded():
    config = json.loads((SMOKE1 / "config.json").read_text())
    for name, rec in config["scenarios"].items():
        assert load_snapshot(SMOKE1_INPUTS / name).hashes == rec["hashes"], name


def test_smoke1_rescored_from_restored_inputs_reproduces_its_oracle_records():
    """The old run folder is read, never written; its inputs come from the fixture."""
    records = rescore(SMOKE1, inputs_root=SMOKE1_INPUTS)
    assert records
    for key, rec in records.items():
        stored = json.loads((SMOKE1 / key / "oracle.json").read_text())
        assert behaviour(rec) == behaviour(stored), key
