"""Mutators: named edits to untrusted inputs, applied to copies inside a run folder. No LLM.

A mutation edits one server's pinned MCP manifest. `mutate` never touches the pinned files: it snapshots
the scenario's clean inputs into `dest`, writes the edited manifest there (same JSON formatting as the
pin, so the bytes differ only where the edit does), keeps the pinned manifests under `pinned_manifests/`
for scoring, and regenerates the schema from the mutated manifests with the scenario's stub:

  structural = False  the regenerated schema must be byte-identical to the pinned one, or MutationError
                      (the claim "this edit is invisible to the schema generator" is checked, not assumed);
  structural = True   the regenerated generated schema and its link with the trusted part replace the
                      pinned ones in `dest`.

kind: "probe" (benign; measures requests newly denied) or "attack" (adversarial; requests newly allowed).
Ops are domain-agnostic; named instances live in a domain's mutations.yaml.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from pgi import schemagen
from pgi.generators.inputs import ScenarioInputs, sha256
from pgi.runs.snapshot import _layout, _write_index, load_snapshot, snapshot


class MutationError(Exception):
    """A mutation's target is missing, it changes nothing, or it changes the schema without saying so."""


@dataclass(frozen=True)
class Mutation:
    name: str
    kind: str          # probe | attack
    server: str
    description: str
    structural: bool   # declared: does the edit change what the schema generator reads?
    edit: Callable[[dict], None]  # edits a copy of the manifest in place; raises MutationError if its target is missing

    def as_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "server": self.server, "description": self.description,
                "structural": self.structural}


def _tool(manifest: dict, name: str) -> dict:
    for t in manifest.get("tools", []):
        if t.get("name") == name:
            return t
    raise MutationError(f"no tool {name!r} in the manifest")


def strip_default(name: str, kind: str, server: str, tool: str, field: str, description: str = "") -> Mutation:
    """Remove `default` from one top-level argument of one tool; nothing else."""
    def edit(m: dict) -> None:
        props = (_tool(m, tool).get("inputSchema") or {}).get("properties") or {}
        if field not in props:
            raise MutationError(f"{tool} has no argument {field!r}")
        if "default" not in props[field]:
            raise MutationError(f"{tool}.{field} declares no default")
        del props[field]["default"]
    return Mutation(name, kind, server, description or f"remove the default of {tool}.{field}", False, edit)


OPS: dict[str, Callable[..., Mutation]] = {"strip_default": strip_default}


def load_mutations(path: Path) -> dict[str, Mutation]:
    """Named mutations from a domain's mutations.yaml: {name: {op, kind, server, description, <op args>}}."""
    out = {}
    for name, spec in (yaml.safe_load(Path(path).read_text()) or {}).items():
        spec = dict(spec)
        op = spec.pop("op")
        if op not in OPS:
            raise MutationError(f"{name}: unknown op {op!r}; known: {sorted(OPS)}")
        out[name] = OPS[op](name, **spec)
    return out


def _changed_paths(a, b, path: str = "") -> list[str]:
    """Paths where two JSON trees differ; tools are addressed by name, other lists by index."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b), key=str):
            p = f"{path}.{k}" if path else str(k)
            if k == "tools" and isinstance(a.get(k), list) and isinstance(b.get(k), list):
                ta, tb = {t.get("name"): t for t in a[k]}, {t.get("name"): t for t in b[k]}
                for n in sorted(set(ta) | set(tb), key=str):
                    out += _changed_paths(ta.get(n, ...), tb.get(n, ...), f"{p}[{n}]")
            elif k not in a or k not in b:
                out.append(p)
            else:
                out += _changed_paths(a[k], b[k], p)
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [x for i, (u, v) in enumerate(zip(a, b)) for x in _changed_paths(u, v, f"{path}[{i}]")]
    return [] if a == b else [path]


def _dumps(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"  # the pinned files' own formatting


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def mutate(mutation: Mutation, inputs: ScenarioInputs, dest: Path) -> tuple[ScenarioInputs, dict]:
    """Mutated inputs snapshotted at dest (which must not exist), and the mutation record (also dest/mutation.json).

    `inputs` must be a live scenario (domain/scenarios/<name>) whose scenario.yaml declares
    `schema_build: {stub: ...}` and one generated and one trusted schema part.
    """
    dest = Path(dest)
    if inputs.pinned_manifest_paths:
        raise MutationError("inputs are already mutated; mutate the pinned scenario")
    if mutation.server not in inputs.servers:
        raise MutationError(f"{mutation.name}: server {mutation.server!r} not in {inputs.servers}")
    domain = inputs.folder.parents[1]
    build = (yaml.safe_load((inputs.folder / "scenario.yaml").read_text()) or {}).get("schema_build") or {}
    if "stub" not in build:
        raise MutationError(f"{inputs.folder}/scenario.yaml declares no schema_build.stub")
    gen_parts, trusted_parts = inputs.schema_parts.get("generated", ()), inputs.schema_parts.get("trusted", ())
    if len(gen_parts) != 1 or len(trusted_parts) != 1:
        raise MutationError(f"need exactly one generated and one trusted schema part, got {inputs.schema_parts}")
    stub = domain / build["stub"]

    i = inputs.servers.index(mutation.server)
    pinned_text = inputs.manifest_paths[i].read_text()
    original = json.loads(pinned_text)
    if _dumps(original) != pinned_text:
        raise MutationError(f"{inputs.manifest_paths[i]} is not in the expected JSON formatting")
    edited = copy.deepcopy(original)
    mutation.edit(edited)
    changed = _changed_paths(original, edited)
    if not changed:
        raise MutationError(f"{mutation.name} is a no-op on {mutation.server}")

    snap = snapshot(inputs, dest)  # clean copies of everything, hash-checked
    (dest / f"manifests/{mutation.server}.tools.json").write_text(_dumps(edited))
    (dest / "pinned_manifests").mkdir()
    for s, p in zip(inputs.servers, inputs.manifest_paths):
        (dest / f"pinned_manifests/{s}.tools.json").write_bytes(p.read_bytes())

    gen_path = dest / "schema_parts" / "generated" / gen_parts[0].name
    pinned_gen = gen_path.read_text()
    regen = schemagen.generate(stub, [dest / f"manifests/{s}.tools.json" for s in inputs.servers])
    identical = regen == pinned_gen
    if not identical and not mutation.structural:
        raise MutationError(f"{mutation.name} is declared non-structural but the regenerated schema differs")
    if not identical:
        gen_path.write_text(regen)
    final = schemagen.link(gen_path, dest / "schema_parts" / "trusted" / trusted_parts[0].name)
    if identical and final != snap.schema_text:
        raise MutationError("regenerated schema is identical but its link differs from the pinned final schema")
    (dest / "schema" / inputs.schema_path.name).write_text(final)

    parts = {r: [p.name for p in ps] for r, ps in inputs.schema_parts.items()}
    layout = _layout(inputs.schema_path.name, list(inputs.servers), parts, pinned=True)
    hashes = {k: sha256(dest / rel) for k, rel in layout.items()}
    _write_index(dest, inputs.name, inputs.schema_path.name, list(inputs.servers), hashes, parts, pinned=True)
    mutated = load_snapshot(dest)
    record = {**mutation.as_dict(), "scenario": inputs.name, "changed_paths": changed,
              "manifest": {"path": f"manifests/{mutation.server}.tools.json",
                           "pinned_sha256": inputs.hashes[f"manifest:{mutation.server}"],
                           "mutated_sha256": hashes[f"manifest:{mutation.server}"]},
              "schema": {"generated_identical": identical, "pinned_generated_sha256": _sha_text(pinned_gen),
                         "regenerated_sha256": _sha_text(regen), "final_sha256": hashes["schema"],
                         "pinned_final_sha256": inputs.hashes["schema"], "stub_sha256": sha256(stub),
                         "generator_config": schemagen.CONFIG}}
    (dest / "mutation.json").write_text(json.dumps(record, indent=1) + "\n")
    return mutated, record
