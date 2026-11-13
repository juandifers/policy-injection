"""Copy every input a score depends on into a run folder, and load scenario inputs back from there.

Layout of runs/<id>/inputs/<scenario>/ (domain-agnostic):

    inputs.json            name, schema (relative path), servers, sha256 of every file below
    scenario.yaml          verbatim copy (its `schema` path refers to the source domain, kept for the hash)
    intent.md  reference.cedar  universe.yaml
    schema/<schema file>
    manifests/<server>.tools.json
    schema_parts/<role>/<file>   optional: the files the linked schema was built from (provenance only)

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


def _layout(schema_name: str, servers: list[str], parts: dict[str, list[str]] | None = None) -> dict[str, str]:
    """Hash key -> path relative to the snapshot folder (keys match ScenarioInputs.hashes)."""
    return {**SCENARIO_FILES, "schema": f"schema/{schema_name}",
            **{f"manifest:{s}": f"manifests/{s}.tools.json" for s in servers},
            **{f"schema_part:{r}:{n}": f"schema_parts/{r}/{n}" for r, ns in (parts or {}).items() for n in ns}}


def _write_index(dest: Path, name: str, schema_name: str, servers: list[str], hashes: dict[str, str],
                 parts: dict[str, list[str]] | None = None, note: str | None = None) -> None:
    index = {"name": name, "schema": f"schema/{schema_name}", "servers": servers, "sha256": hashes,
             "schema_parts": parts or {}}
    if note:
        index["note"] = note
    (dest / "inputs.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")


def snapshot(inputs: ScenarioInputs, dest: Path) -> ScenarioInputs:
    """Copy one scenario's inputs into dest (which must not exist) and return them loaded from there."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=False)
    parts = {r: [p.name for p in ps] for r, ps in inputs.schema_parts.items()}
    sources = {**{k: inputs.folder / f for k, f in SCENARIO_FILES.items()}, "schema": inputs.schema_path,
               **{f"manifest:{s}": p for s, p in zip(inputs.servers, inputs.manifest_paths)},
               **{f"schema_part:{r}:{p.name}": p for r, ps in inputs.schema_parts.items() for p in ps}}
    layout = _layout(inputs.schema_path.name, list(inputs.servers), parts)
    if set(sources) != set(inputs.hashes):
        raise SnapshotError(f"inputs hash keys {sorted(inputs.hashes)} != snapshot files {sorted(sources)}")
    for key, rel in layout.items():
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sources[key], dest / rel)
    _write_index(dest, inputs.name, inputs.schema_path.name, list(inputs.servers), inputs.hashes, parts)
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
    parts = index.get("schema_parts") or {}
    layout = _layout(Path(index["schema"]).name, servers, parts)
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
                          (folder / "intent.md").read_text(), hashes,
                          {r: tuple(folder / layout[f"schema_part:{r}:{n}"] for n in ns) for r, ns in parts.items()})


def _git_show(repo: Path, commit: str, path: str) -> bytes:
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"], capture_output=True)
    if proc.returncode != 0:
        raise SnapshotError(f"git show {commit}:{path} failed: {proc.stderr.decode().strip()}")
    return proc.stdout


def snapshot_from_git(repo: Path, commit: str, scenario: str, dest: Path, expected: dict[str, str]) -> ScenarioInputs:
    """Rebuild a snapshot from git for a run that predates snapshots.

    scenario: the scenario folder relative to the repo (<domain>/scenarios/<name>, same convention as
    load_scenario_inputs). expected: the hashes that run recorded; any difference raises SnapshotError.
    If the scenario.yaml at that commit declares no schema_parts, the parts named by the *current*
    scenario.yaml are read at that commit (unhashed by the old run; recorded in inputs.json as a note).
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=False)
    domain = Path(scenario).parents[1]
    meta = yaml.safe_load(_git_show(repo, commit, f"{scenario}/scenario.yaml"))
    servers = list(meta["servers"])
    schema_rel = domain / meta["schema"]
    sources = {**{k: f"{scenario}/{f}" for k, f in SCENARIO_FILES.items()}, "schema": str(schema_rel),
               **{f"manifest:{s}": str(domain / "manifests" / f"{s}.tools.json") for s in servers}}
    note = None
    part_meta = meta.get("schema_parts")
    if not part_meta:
        current = Path(repo) / scenario / "scenario.yaml"
        part_meta = (yaml.safe_load(current.read_text()) or {}).get("schema_parts") if current.is_file() else None
        if part_meta:
            note = (f"schema_parts paths from the current scenario.yaml, content from git {commit}; "
                    "the source run did not record their hashes")
    parts = {r: [Path(f).name for f in fs] for r, fs in (part_meta or {}).items()}
    sources |= {f"schema_part:{r}:{Path(f).name}": str(domain / f) for r, fs in (part_meta or {}).items() for f in fs}
    hashes = dict(expected)
    for key, rel in _layout(schema_rel.name, servers, parts).items():
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        (dest / rel).write_bytes(_git_show(repo, commit, sources[key]))
        if key not in hashes:  # schema parts the old run never hashed
            hashes[key] = sha256(dest / rel)
    _write_index(dest, Path(scenario).name, schema_rel.name, servers, hashes, parts, note)
    return load_snapshot(dest)  # verifies every file against the run's recorded hashes
