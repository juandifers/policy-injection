"""Mutators edit a copy of a pinned manifest inside a run folder; pinned files are never touched."""

import dataclasses
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from pgi.analysis.defaults import default_reliance
from pgi.generators.inputs import load_scenario_inputs
from pgi.mutators import Mutation, MutationError, load_mutations, mutate, strip_default
from pgi.oracle import validation
from pgi.oracle.enumeration import load_universe
from pgi.runs.snapshot import load_snapshot

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domains" / "assetopsbench"
S02 = DOMAIN / "scenarios" / "s02_site_scoped_reads"
BASELINE = ROOT / "runs" / "20261113T155356Z-clean"

pytestmark = pytest.mark.skipif(shutil.which("cedar") is None, reason="cedar CLI not on PATH")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture
def probe():
    return load_mutations(DOMAIN / "mutations.yaml")["strip-default-open_only"]


def test_registry_declares_the_probe(probe):
    assert (probe.name, probe.kind, probe.server, probe.structural) == ("strip-default-open_only", "probe", "wo", False)


def test_strip_default_removes_exactly_one_key_and_never_touches_the_pin(tmp_path, probe):
    pinned = {p: _sha(p) for p in (DOMAIN / "manifests").glob("*.json")} | \
             {p: _sha(p) for p in (DOMAIN / "schema").glob("*.cedarschema")}
    inp = load_scenario_inputs(S02)
    mutated, record = mutate(probe, inp, tmp_path / "inputs" / S02.name)
    assert {p: _sha(p) for p in pinned} == pinned                                  # pinned files untouched
    assert record["changed_paths"] == ["tools[get_my_assigned_workorders].inputSchema.properties.open_only.default"]
    assert record["manifest"]["pinned_sha256"] == inp.hashes["manifest:wo"]
    assert record["manifest"]["mutated_sha256"] == mutated.hashes["manifest:wo"] != inp.hashes["manifest:wo"]
    m = json.loads(mutated.manifest_paths[0].read_text())
    t = next(t for t in m["tools"] if t["name"] == "get_my_assigned_workorders")
    assert "default" not in t["inputSchema"]["properties"]["open_only"]
    assert mutated.manifest_paths[0].is_relative_to(tmp_path)
    assert mutated.manifest_paths[1].read_bytes() == inp.manifest_paths[1].read_bytes()   # iot copied unchanged


def test_non_structural_probe_regenerates_an_identical_schema(tmp_path, probe):
    inp = load_scenario_inputs(S02)
    mutated, record = mutate(probe, inp, tmp_path / "inputs" / S02.name)
    assert record["schema"]["generated_identical"] is True
    assert mutated.schema_text == inp.schema_text
    gen = mutated.schema_parts["generated"][0]
    assert gen.read_bytes() == inp.schema_parts["generated"][0].read_bytes()
    assert load_snapshot(mutated.folder) == mutated                                # hash-checked snapshot


def test_scoring_keeps_the_pinned_defaults(tmp_path, probe):
    """The server still defaults open_only to true, so the detector reads the pinned manifests."""
    mutated, _ = mutate(probe, load_scenario_inputs(S02), tmp_path / "inputs" / S02.name)
    assert [p.read_bytes() for p in mutated.pinned_manifest_paths] == \
           [p.read_bytes() for p in load_scenario_inputs(S02).manifest_paths]
    policy = BASELINE / "s02_site_scoped_reads" / "sondera" / "sample_00" / "policy.cedar"
    rows = default_reliance(policy, load_universe(mutated.universe), mutated.schema_path, mutated.defaults_manifests)
    assert [r["verdict"] for r in rows if r["field"] == "open_only"] == ["relies"]


def test_a_non_structural_edit_that_changes_the_schema_is_refused(tmp_path):
    def rename(m):
        props = next(t for t in m["tools"] if t["name"] == "get_my_assigned_workorders")["inputSchema"]["properties"]
        props["only_open"] = props.pop("open_only")
    bad = Mutation("rename", "probe", "wo", "renames a field", False, rename)
    with pytest.raises(MutationError, match="schema"):
        mutate(bad, load_scenario_inputs(S02), tmp_path / "inputs" / S02.name)


def test_a_structural_edit_regenerates_and_links_the_schema_in_the_run_folder(tmp_path):
    def add(m):
        props = next(t for t in m["tools"] if t["name"] == "get_my_assigned_workorders")["inputSchema"]["properties"]
        props["limit"] = {"type": "integer", "title": "Limit"}
    mut = Mutation("add-limit", "attack", "wo", "adds a field", True, add)
    inp = load_scenario_inputs(S02)
    mutated, record = mutate(mut, inp, tmp_path / "inputs" / S02.name)
    assert record["schema"]["generated_identical"] is False
    assert mutated.schema_path.is_relative_to(tmp_path) and mutated.schema_text != inp.schema_text
    assert "limit" in mutated.schema_parts["generated"][0].read_text()
    pol = tmp_path / "p.cedar"
    pol.write_text('permit (principal, action == AOB::Action::"get_my_assigned_workorders", resource)\n'
                   'when { context.input has limit && context.input.limit < 10 };\n')
    assert validation.check(pol, mutated.schema_path).ok
    assert not validation.check(pol, inp.schema_path).ok


def test_mutation_errors(tmp_path):
    inp = load_scenario_inputs(S02)
    for m in (strip_default("strip-x", "probe", "wo", "get_my_assigned_workorders", "labor_code"),  # no default
              strip_default("strip-y", "probe", "wo", "no_such_tool", "open_only"),
              strip_default("strip-z", "probe", "nope", "get_my_assigned_workorders", "open_only")):
        with pytest.raises(MutationError):
            mutate(m, inp, tmp_path / m.name)
    noop = Mutation("noop", "probe", "wo", "changes nothing", False, lambda m: None)
    with pytest.raises(MutationError, match="no-op"):
        mutate(noop, inp, tmp_path / "noop")


def test_mutated_inputs_feed_the_generator_prompt(tmp_path, probe):
    from pgi.generators import naive
    mutated, _ = mutate(probe, load_scenario_inputs(S02), tmp_path / "inputs" / S02.name)
    clean_sys = json.dumps(naive.build_request(load_scenario_inputs(S02), naive.NaiveConfig("m"))[1]["system"])
    probe_sys = json.dumps(naive.build_request(mutated, naive.NaiveConfig("m"))[1]["system"])
    assert clean_sys != probe_sys
    assert clean_sys.count('\\"default\\": true') == probe_sys.count('\\"default\\": true') + 1
