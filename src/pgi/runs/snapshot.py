"""Copy every input a score depends on into a run folder, and load scenario inputs back from there.

Layout of runs/<id>/inputs/<scenario>/ (domain-agnostic):

    inputs.json            name, schema (relative path), servers, sha256 of every file below
    scenario.yaml          verbatim copy (its `schema` path refers to the source domain, kept for the hash)
    intent.md  reference.cedar  universe.yaml
    schema/<schema file>
    manifests/<server>.tools.json

`load_snapshot` re-hashes every file and raises SnapshotError on any mismatch, so a snapshot that has
been edited can never be scored silently. `snapshot_from_git` rebuilds the same layout for a run that
predates snapshots, from `git show <commit>:<path>`, and checks the hashes that run recorded.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import yaml

from pgi.generators.inputs import ScenarioInputs, sha256

SCENARIO_FILES = {"scenario_yaml": "scenario.yaml", "intent": "intent.md",
                  "reference": "reference.cedar", "universe": "universe.yaml"}


class SnapshotError(Exception):
    """A snapshot is missing a file or a file's hash differs from the one recorded."""


def _layout(schema_name: str, servers: list[str]) -> dict[str, str]:
    """Hash key -> path relative to the snapshot folder (keys match ScenarioInputs.hashes)."""
    return {**SCENARIO_FILES, "schema": f"schema/{schema_name}",
            **{f"manifest:{s}": f"manifests/{s}.tools.json" for s in servers}}


def _write_index(dest: Path, name: str, schema_name: str, servers: list[str], hashes: dict[str, str]) -> None:
    (dest / "inputs.json").write_text(json.dumps(
        {"name": name, "schema": f"schema/{schema_name}", "servers": servers, "sha256": hashes},
        indent=2, sort_keys=True) + "\n")


def snapshot(inputs: ScenarioInputs, dest: Path) -> ScenarioInputs:
    """Copy one scenario's inputs into dest (which must not exist) and return them loaded from there."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=False)
    sources = {**{k: inputs.folder / f for k, f in SCENARIO_FILES.items()}, "schema": inputs.schema_path,
               **{f"manifest:{s}": p for s, p in zip(inputs.servers, inputs.manifest_paths)}}
    layout = _layout(inputs.schema_path.name, list(inputs.servers))
    if set(sources) != set(inputs.hashes):
        raise SnapshotError(f"inputs hash keys {sorted(inputs.hashes)} != snapshot files {sorted(sources)}")
    for key, rel in layout.items():
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sources[key], dest / rel)
    _write_index(dest, inputs.name, inputs.schema_path.name, list(inputs.servers), inputs.hashes)
    snap = load_snapshot(dest)
    if snap.hashes != inputs.hashes:
        raise SnapshotError(f"{dest}: copied files do not hash like their sources")
    return snap


def load_snapshot(folder: Path) -> ScenarioInputs:
    """ScenarioInputs read only from a snapshot folder; raises SnapshotError unless every hash matches."""
    folder = Path(folder)
    index_path = folder / "inputs.json"
    if not index_path.is_file():
        raise SnapshotError(f"{folder}: no inputs.json (not a snapshot)")
    index = json.loads(index_path.read_text())
    servers = list(index["servers"])
    layout = _layout(Path(index["schema"]).name, servers)
    if set(layout) != set(index["sha256"]):
        raise SnapshotError(f"{folder}: inputs.json lists {sorted(index['sha256'])}, expected {sorted(layout)}")
    hashes = {}
    for key, rel in layout.items():
        path = folder / rel
        if not path.is_file():
            raise SnapshotError(f"{folder}: missing {rel} ({key})")
        hashes[key] = sha256(path)
        if hashes[key] != index["sha256"][key]:
            raise SnapshotError(f"{folder}: {rel} ({key}) changed since the snapshot was taken")
    schema = folder / index["schema"]
    return ScenarioInputs(index["name"], folder, schema, schema.read_text(), tuple(servers),
                          tuple(folder / layout[f"manifest:{s}"] for s in servers),
                          (folder / "intent.md").read_text(), hashes)


def _git_show(repo: Path, commit: str, path: str) -> bytes:
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"], capture_output=True)
    if proc.returncode != 0:
        raise SnapshotError(f"git show {commit}:{path} failed: {proc.stderr.decode().strip()}")
    return proc.stdout


def snapshot_from_git(repo: Path, commit: str, scenario: str, dest: Path, expected: dict[str, str]) -> ScenarioInputs:
    """Rebuild a snapshot from git for a run that predates snapshots.

    scenario: the scenario folder relative to the repo (<domain>/scenarios/<name>, same convention as
    load_scenario_inputs). expected: the hashes that run recorded; any difference raises SnapshotError.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=False)
    domain = Path(scenario).parents[1]
    meta = yaml.safe_load(_git_show(repo, commit, f"{scenario}/scenario.yaml"))
    servers = list(meta["servers"])
    schema_rel = domain / meta["schema"]
    sources = {**{k: f"{scenario}/{f}" for k, f in SCENARIO_FILES.items()}, "schema": str(schema_rel),
               **{f"manifest:{s}": str(domain / "manifests" / f"{s}.tools.json") for s in servers}}
    for key, rel in _layout(schema_rel.name, servers).items():
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        (dest / rel).write_bytes(_git_show(repo, commit, sources[key]))
    _write_index(dest, Path(scenario).name, schema_rel.name, servers, expected)
    return load_snapshot(dest)  # verifies every file against the run's recorded hashes
