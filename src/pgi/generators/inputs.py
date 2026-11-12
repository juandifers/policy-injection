"""What a generator may see for one scenario, loaded from the paths its scenario.yaml names.

Layout convention (domain-agnostic): <domain>/scenarios/<scenario>/scenario.yaml names `schema`
(relative to <domain>) and `servers`; manifests live at <domain>/manifests/<server>.tools.json.
The reference and universe are hashed for the run record but are never given to a generator.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

_SUBSCHEMA_MAPS = ("properties", "$defs", "definitions", "patternProperties")
_SUBSCHEMA_ONE = ("items", "additionalProperties", "not", "if", "then", "else", "contains")
_SUBSCHEMA_LISTS = ("anyOf", "oneOf", "allOf", "prefixItems")


def sha256(path: Path) -> str:
    """Hex SHA-256 of a file's bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class ScenarioInputs:
    """The trusted intent and the (untrusted) schema and manifests for one scenario, with input hashes."""

    name: str
    folder: Path
    schema_path: Path
    schema_text: str
    servers: tuple[str, ...]
    manifest_paths: tuple[Path, ...]
    intent: str
    hashes: dict[str, str]

    @property
    def reference(self) -> Path:
        return self.folder / "reference.cedar"

    @property
    def universe(self) -> Path:
        return self.folder / "universe.yaml"


def load_scenario_inputs(folder: Path) -> ScenarioInputs:
    """Load a scenario's generator inputs and hash every file that can influence a result."""
    folder = Path(folder)
    domain = folder.parents[1]
    meta = yaml.safe_load((folder / "scenario.yaml").read_text())
    schema = domain / meta["schema"]
    servers = tuple(meta["servers"])
    manifests = tuple(domain / "manifests" / f"{s}.tools.json" for s in servers)
    hashes = {"schema": sha256(schema), "intent": sha256(folder / "intent.md"),
              "reference": sha256(folder / "reference.cedar"), "universe": sha256(folder / "universe.yaml"),
              "scenario_yaml": sha256(folder / "scenario.yaml")}
    hashes |= {f"manifest:{s}": sha256(p) for s, p in zip(servers, manifests)}
    return ScenarioInputs(folder.name, folder, schema, schema.read_text(), servers, manifests,
                          (folder / "intent.md").read_text(), hashes)


def _strip_schema(node: object) -> None:
    """Remove `description` annotations from a JSON Schema node in place, never property names."""
    if isinstance(node, list):
        for item in node:
            _strip_schema(item)
        return
    if not isinstance(node, dict):
        return
    if isinstance(node.get("description"), str):
        del node["description"]
    for key, value in node.items():
        if key in _SUBSCHEMA_MAPS and isinstance(value, dict):
            for child in value.values():
                _strip_schema(child)
        elif key in _SUBSCHEMA_ONE or key in _SUBSCHEMA_LISTS:
            _strip_schema(value)


def strip_descriptions(manifest: dict) -> dict:
    """A copy of a tools/list manifest with every tool and JSON Schema `description` removed."""
    out = copy.deepcopy(manifest)
    for tool in out.get("tools", []):
        tool.pop("description", None)
        for key in ("inputSchema", "outputSchema"):
            if key in tool:
                _strip_schema(tool[key])
    return out
