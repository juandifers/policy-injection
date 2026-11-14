"""Depth-1 schema observer: does a manifest edit reach the generated Cedar schema? Domain-agnostic; no LLM.

`observe` regenerates the schema for the clean manifests and for the mutated ones through pgi.schemagen.generate
(the same path as domains/*/scripts/gen_schema.py), diffs the two texts and classifies:

  schema_changed    the edit reached the schema (names, types, required, enum, format, anyOf order);
  schema_unchanged  the generator is blind to it (free text, defaults, unknown keys).

`expected(channel)` is the prediction the Step 2 table in docs/findings.md makes for a channel, and
`SchemaEffect.agrees_with(channel)` says whether an observation matches it, so a mislabelled edit shows up.
Depth 1 means the generated schema text only: not the linked final schema, not any policy.

`observe_edit` is the run-folder form: apply one EditSpec, write the mutated copy, the EditRecord, the effect
and both schema texts under `dest` (which must not exist). Pinned files are only read.
"""

from __future__ import annotations

import difflib
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from pgi import schemagen
from pgi.mutators.edit import CHANNELS, EditRecord, EditSpec, apply

CLASSIFICATIONS = ("schema_changed", "schema_unchanged")


@dataclass(frozen=True)
class SchemaEffect:
    classification: str
    clean_sha256: str
    mutated_sha256: str
    diff: list[str]          # unified diff of the generated schema text, clean -> mutated; [] when unchanged

    def agrees_with(self, channel: str) -> bool:
        return self.classification == expected(channel)

    def as_dict(self) -> dict:
        return asdict(self)


def expected(channel: str) -> str:
    """What the Step 2 table predicts for a channel: only the structure channel reaches the schema."""
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel {channel!r}; known: {sorted(CHANNELS)}")
    return "schema_changed" if channel == "structure" else "schema_unchanged"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def classify(clean: str, mutated: str) -> SchemaEffect:
    """Compare two generated schema texts."""
    diff = list(difflib.unified_diff(clean.splitlines(), mutated.splitlines(), "clean", "mutated", lineterm=""))
    return SchemaEffect("schema_unchanged" if clean == mutated else "schema_changed", _sha(clean), _sha(mutated), diff)


def observe(stub: Path, clean_manifests: list[Path], mutated_manifests: list[Path]) -> SchemaEffect:
    """Regenerate from both manifest lists (same servers, same order) and classify the difference."""
    if len(clean_manifests) != len(mutated_manifests):
        raise ValueError("clean and mutated manifest lists must align")
    return classify(schemagen.generate(stub, list(clean_manifests)), schemagen.generate(stub, list(mutated_manifests)))


def write_manifest(manifest: dict, path: Path) -> None:
    """Write a manifest in the pinned files' own JSON formatting; never overwrites."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} exists; mutated manifests are never overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def observe_edit(stub: Path, manifests: list[Path], index: int, spec: EditSpec, dest: Path) -> tuple[EditRecord, SchemaEffect]:
    """Apply `spec` to manifests[index], regenerate, and record everything under `dest` (must not exist).

    dest/manifests/<name>                  the mutated copy (pin formatting)
    dest/schema/clean.generated.cedarschema, mutated.generated.cedarschema
    dest/edit.json                         spec, record, effect, manifest paths and hashes, generator config
    """
    dest, manifests = Path(dest), [Path(p) for p in manifests]
    if dest.exists():
        raise FileExistsError(f"{dest} exists; run folders are never overwritten")
    clean_text = manifests[index].read_text()
    mutated, record = apply(json.loads(clean_text), spec)
    dest.mkdir(parents=True)
    out = dest / "manifests" / manifests[index].name
    write_manifest(mutated, out)
    mutated_paths = [out if i == index else p for i, p in enumerate(manifests)]
    clean_schema = schemagen.generate(stub, manifests)
    mutated_schema = schemagen.generate(stub, mutated_paths)
    effect = classify(clean_schema, mutated_schema)
    (dest / "schema").mkdir()
    (dest / "schema" / "clean.generated.cedarschema").write_text(clean_schema)
    (dest / "schema" / "mutated.generated.cedarschema").write_text(mutated_schema)
    record_doc = {
        "spec": spec.as_dict(),
        "record": record.as_dict(),
        "effect": effect.as_dict(),
        "expected": expected(spec.channel),
        "agrees": effect.agrees_with(spec.channel),
        "manifests": {"clean": [str(p) for p in manifests],
                      "clean_sha256": [hashlib.sha256(p.read_bytes()).hexdigest() for p in manifests],
                      "mutated": f"manifests/{out.name}",
                      "mutated_sha256": hashlib.sha256(out.read_bytes()).hexdigest()},
        "stub_sha256": hashlib.sha256(Path(stub).read_bytes()).hexdigest(),
        "generator_config": schemagen.CONFIG,
    }
    (dest / "edit.json").write_text(json.dumps(record_doc, indent=1) + "\n")
    return record, effect
