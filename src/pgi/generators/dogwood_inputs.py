"""What a Dogwood (temporal-track) generator may see for one scenario, and the run-folder snapshot of it. Domain-agnostic.

scenario.yaml (track: dogwood) names, relative to <domain>: `schema` (action schema), `event_schema`, and `manifests`
(server -> file); relative to the scenario folder: `intent`, `gold`, `traces` (traces.yaml) and optionally
`requirements` (witness traces per contract requirement, scoring only) and `catalogue` (Phase 2c: the trusted admission
catalogue beside the written contract, read by pgi.analysis.admission and by the BIND/TOKEN tally for the protected
action). The gold policy, the suite, the requirements and the catalogue are hashed for the run record and are never
given to a generator.

Selectable arms (Phase 2a-bis, 2b): `intents` (name -> intent file, `--intent`) and `arms` (name -> overrides of
`manifests` (per server), `schema`, `gold`, `traces`, `requirements`; `--arm`). An arm inherits every key it does not
override. The base inputs are the files named at the top level; "base" is the arm name when none is selected.

Snapshot layout, runs/<id>/inputs/<scenario>/:
    inputs.json  scenario.yaml  intent.md  gold.dw  traces.yaml  traces/<file>  requirements.yaml?  catalogue.yaml?
    schema/<file>  event_schema/<file>  manifests/<server>.tools.json
`load_snapshot` re-hashes every file and raises SnapshotError on any mismatch.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from pgi.generators.inputs import sha256
from pgi.oracle.temporal import TraceSuite, load_suite


class SnapshotError(Exception):
    """A snapshot is missing a file or a file's hash differs from the one recorded."""


@dataclass(frozen=True)
class DogwoodInputs:
    """Trusted intent, (untrusted) schema and manifests, event schema; plus scoring files, with input hashes."""

    name: str
    folder: Path
    schema_path: Path
    schema_text: str
    event_schema_path: Path
    event_schema_text: str
    servers: tuple[str, ...]
    manifest_paths: tuple[Path, ...]
    intent_name: str          # which intent arm (key of scenario.yaml `intents`, or the file name)
    intent_path: Path
    intent: str
    gold: Path
    traces_yaml: Path
    requirements: Path | None
    hashes: dict[str, str]
    arm_name: str = "base"    # which manifest arm (key of scenario.yaml `arms`), "base" for the top-level files
    catalogue: Path | None = None   # trusted admission catalogue (scenario.yaml `catalogue`), scoring/analysis only


@dataclass(frozen=True)
class Requirements:
    """Scoring metadata, all behaviour over suite traces (requirements.yaml):
    - a policy reconstructs requirement `name` iff it allows `base` and denies every one of its witnesses;
    - it is over-permissive iff it allows any of `over_permissive_if_allows`, over-strict iff it denies any of
      `over_strict_if_denies`;
    - it accepts evidence source `s` iff it allows the single-source trace `sources[s]`;
    - `prerequisite` = (trace, decision index) of the evidence call itself, or None;
    - Phase 2b: `vendor_only` = contract-deny traces whose only evidence is the vendor's (primary outcome: allows any);
      `vocabulary` = the evidence-vocabulary classification inputs for pgi.analysis.dogwood_text.vocabulary_report
      (authority_action, vendor_actions, contract_values, vendor_stated_values, approver_kind_fields), text-level, or None."""

    base: str
    witnesses: dict[str, tuple[str, ...]]
    numbers: dict[str, int]
    over_permissive_if_allows: tuple[str, ...] = ()
    over_strict_if_denies: tuple[str, ...] = ()
    sources: dict[str, str] = None  # type: ignore[assignment]
    prerequisite: tuple[str, int] | None = None
    vendor_only: tuple[str, ...] = ()
    vocabulary: dict | None = None


VOCABULARY_KEYS = ("authority_action", "vendor_actions", "contract_values", "vendor_stated_values", "approver_kind_fields")


def _hash_all(files: dict[str, Path]) -> dict[str, str]:
    return {k: sha256(p) for k, p in files.items()}


def _files(folder: Path, schema: Path, event_schema: Path, servers: list[str], manifests: list[Path], intent: Path,
           gold: Path, traces_yaml: Path, requirements: Path | None, catalogue: Path | None = None) -> dict[str, Path]:
    """Hash key -> file, including every trace of the suite."""
    suite = load_suite(traces_yaml)
    files = {"scenario_yaml": folder / "scenario.yaml", "intent": intent, "gold": gold, "traces_yaml": traces_yaml,
             "schema": schema, "event_schema": event_schema,
             **{f"manifest:{s}": p for s, p in zip(servers, manifests)},
             **{f"trace:{tid}": p for tid, p in suite.traces.items()}}
    if requirements is not None:
        files["requirements"] = requirements
    if catalogue is not None:
        files["catalogue"] = catalogue
    return files


def load_dogwood_inputs(folder: Path, intent: str | None = None, arm: str | None = None) -> DogwoodInputs:
    """Load a temporal scenario's inputs from its folder and hash every file that can influence a result.

    `intent` selects an arm from scenario.yaml `intents` (name -> file); None takes the default `intent` file.
    `arm` selects a manifest arm from scenario.yaml `arms` (overrides of manifests/schema/gold/traces/requirements);
    None takes the top-level files ("base").
    """
    folder = Path(folder)
    domain = folder.parents[1]
    meta = yaml.safe_load((folder / "scenario.yaml").read_text())
    if meta.get("track") != "dogwood":
        raise ValueError(f"{folder}: scenario.yaml must declare `track: dogwood` (got {meta.get('track')!r})")
    manifest_arms = dict(meta.get("arms") or {})
    if arm is None:
        spec, arm_name = {}, "base"
    elif arm in manifest_arms:
        spec, arm_name = dict(manifest_arms[arm] or {}), arm
    else:
        raise ValueError(f"{folder}: no manifest arm {arm!r} in scenario.yaml `arms` {sorted(manifest_arms)}")
    if unknown := set(spec) - {"manifests", "schema", "gold", "traces", "requirements", "catalogue"}:
        raise ValueError(f"{folder}: arm {arm!r} overrides unknown keys {sorted(unknown)}")
    servers = list(meta["servers"])
    arm_manifests = dict(spec.get("manifests") or {})
    if unknown := set(arm_manifests) - set(servers):
        raise ValueError(f"{folder}: arm {arm!r} names servers not in the scenario: {sorted(unknown)}")
    manifests = [domain / arm_manifests.get(s, meta["manifests"][s]) for s in servers]
    schema, events = domain / spec.get("schema", meta["schema"]), domain / meta["event_schema"]
    arms = dict(meta.get("intents") or {})
    default = meta.get("intent", "intent.md")
    if intent is None:
        intent_file, intent_name = default, next((k for k, v in arms.items() if v == default), Path(default).name)
    elif intent in arms:
        intent_file, intent_name = arms[intent], intent
    else:
        raise ValueError(f"{folder}: no intent arm {intent!r} in scenario.yaml `intents` {sorted(arms)}")
    intent_path = folder / intent_file
    gold, traces = folder / spec.get("gold", meta["gold"]), folder / spec.get("traces", meta["traces"])
    reqs_file = spec.get("requirements", meta.get("requirements"))
    reqs = folder / reqs_file if reqs_file else None
    cat_file = spec.get("catalogue", meta.get("catalogue"))
    catalogue = folder / cat_file if cat_file else None
    files = _files(folder, schema, events, servers, manifests, intent_path, gold, traces, reqs, catalogue)
    return DogwoodInputs(folder.name, folder, schema, schema.read_text(), events, events.read_text(), tuple(servers),
                         tuple(manifests), intent_name, intent_path, intent_path.read_text(), gold, traces, reqs, _hash_all(files),
                         arm_name, catalogue)


def load_requirements(path: Path, suite: TraceSuite) -> Requirements:
    """Load requirements.yaml; every witness and the base must be traces of the suite."""
    data = yaml.safe_load(Path(path).read_text())
    base = data["base"]
    if base not in suite.ids:
        raise ValueError(f"{path}: base trace {base!r} is not in the suite")
    witnesses, numbers = {}, {}
    for name, spec in data["requirements"].items():
        traces = tuple(spec["witnesses"])
        if unknown := [t for t in traces if t not in suite.ids]:
            raise ValueError(f"{path}: requirement {name!r} names traces not in the suite: {unknown}")
        if not traces:
            raise ValueError(f"{path}: requirement {name!r} has no witnesses")
        witnesses[name], numbers[name] = traces, int(spec["requirement"])

    def known(key: str, traces, want: bool | None) -> tuple[str, ...]:
        traces = tuple(traces)
        if unknown := [t for t in traces if t not in suite.ids]:
            raise ValueError(f"{path}: {key} names traces not in the suite: {unknown}")
        if want is not None and (wrong := [t for t in traces if suite.contract[t] is not want]):
            raise ValueError(f"{path}: {key}: contract of {wrong} is not {'allow' if want else 'deny'}")
        return traces

    sec = data.get("security") or {}
    over_p = known("security.over_permissive_if_allows", sec.get("over_permissive_if_allows", ()), False)
    over_s = known("security.over_strict_if_denies", sec.get("over_strict_if_denies", ()), True)
    sources = {name: known(f"evidence_sources.{name}", [t], None)[0] for name, t in (data.get("evidence_sources") or {}).items()}
    prereq = None
    if pre := data.get("prerequisite_call"):
        prereq = (known("prerequisite_call", [pre["trace"]], None)[0], int(pre["decision_index"]))
    vendor_only = known("vendor_only_traces", data.get("vendor_only_traces", ()), False)
    vocab = data.get("evidence_vocabulary")
    if vocab is not None:
        if set(vocab) != set(VOCABULARY_KEYS):
            raise ValueError(f"{path}: evidence_vocabulary must have exactly the keys {VOCABULARY_KEYS}, got {sorted(vocab)}")
        vocab = {k: (list(v) if isinstance(v, list) else v) for k, v in vocab.items()}
    return Requirements(base, witnesses, numbers, over_p, over_s, sources, prereq, vendor_only, vocab)


def _layout(inputs: DogwoodInputs) -> dict[str, str]:
    """Hash key -> path relative to the snapshot folder (same keys as inputs.hashes)."""
    suite = load_suite(inputs.traces_yaml)
    lay = {"scenario_yaml": "scenario.yaml", "intent": "intent.md", "gold": "gold.dw",
           "traces_yaml": "traces.yaml", "schema": f"schema/{inputs.schema_path.name}",
           "event_schema": f"event_schema/{inputs.event_schema_path.name}",
           **{f"manifest:{s}": f"manifests/{s}.tools.json" for s in inputs.servers},
           **{f"trace:{tid}": str(p.relative_to(inputs.traces_yaml.parent)) for tid, p in suite.traces.items()}}
    if inputs.requirements is not None:
        lay["requirements"] = "requirements.yaml"
    if inputs.catalogue is not None:
        lay["catalogue"] = "catalogue.yaml"
    return lay


def snapshot(inputs: DogwoodInputs, dest: Path) -> DogwoodInputs:
    """Copy one scenario's inputs into dest (which must not exist) and return them loaded from there."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=False)
    suite = load_suite(inputs.traces_yaml)
    sources = _files(inputs.folder, inputs.schema_path, inputs.event_schema_path, list(inputs.servers),
                     list(inputs.manifest_paths), inputs.intent_path, inputs.gold, inputs.traces_yaml, inputs.requirements,
                     inputs.catalogue)
    layout = _layout(inputs)
    if set(sources) != set(inputs.hashes) or set(layout) != set(inputs.hashes):
        raise SnapshotError(f"hash keys {sorted(inputs.hashes)} != files {sorted(sources)} / layout {sorted(layout)}")
    for key, rel in layout.items():
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sources[key], dest / rel)
    index = {"name": inputs.name, "servers": list(inputs.servers), "layout": layout, "sha256": inputs.hashes,
             "intent_name": inputs.intent_name, "intent_source": inputs.intent_path.name, "arm_name": inputs.arm_name,
             "traces": {tid: f"trace:{tid}" for tid in suite.traces}}
    (dest / "inputs.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    snap = load_snapshot(dest)
    if snap.hashes != inputs.hashes:
        raise SnapshotError(f"{dest}: copied files do not hash like their sources")
    return snap


def load_snapshot(folder: Path) -> DogwoodInputs:
    """DogwoodInputs read only from a snapshot folder; raises SnapshotError unless every hash matches."""
    folder = Path(folder)
    index_path = folder / "inputs.json"
    if not index_path.is_file():
        raise SnapshotError(f"{folder}: no inputs.json (not a snapshot)")
    index = json.loads(index_path.read_text())
    layout: dict[str, str] = index["layout"]
    if set(layout) != set(index["sha256"]):
        raise SnapshotError(f"{folder}: inputs.json layout and hashes name different keys")
    hashes = {}
    for key, rel in layout.items():
        path = folder / rel
        if not path.is_file():
            raise SnapshotError(f"{folder}: missing {rel} ({key})")
        hashes[key] = sha256(path)
        if hashes[key] != index["sha256"][key]:
            raise SnapshotError(f"{folder}: {rel} ({key}) changed since the snapshot was taken")
    servers = list(index["servers"])
    schema, events = folder / layout["schema"], folder / layout["event_schema"]
    reqs = folder / layout["requirements"] if "requirements" in layout else None
    cat = folder / layout["catalogue"] if "catalogue" in layout else None
    intent = folder / layout["intent"]
    return DogwoodInputs(index["name"], folder, schema, schema.read_text(), events, events.read_text(), tuple(servers),
                         tuple(folder / layout[f"manifest:{s}"] for s in servers), index.get("intent_name", "intent.md"),
                         intent, intent.read_text(),
                         folder / layout["gold"], folder / layout["traces_yaml"], reqs, hashes, index.get("arm_name", "base"), cat)
