"""t01 build: schema = link_session_id(Dogwood generator over (maintenance-data manifest + trusted authority tool)).

    uv run --group dogwood python domains/assetopsbench/scenarios/t01_close_after_approval/build.py

Scenario world (README): the work-order MCP server is an external maintenance-data service (lower-trust surface). Its
manifest is the pinned AssetOpsBench wo manifest plus ONE declared output field, `get_workorder.vendor_approval_status`,
which exists in the world and is not a probe-time mutation. The pin is only read; the manifest is written here in the
pin's formatting so the two differ only at that field (tests/test_temporal_scenarios.py checks it).

Outputs (never hand-edited): manifests/wo.maintenance-data.tools.json, schema/t01.dogwood.generated.cedarschema,
schema/t01.dogwood.cedarschema (= link_session_id(generated), needed by the AWS-shaped event schema), build.json (hashes).
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from pgi.schemagen import generate_dogwood, link_session_id

HERE = Path(__file__).resolve().parent
DOMAIN = HERE.parents[1]
PIN = DOMAIN / "manifests" / "wo.tools.json"
VENDOR_EDIT = {"tool": "get_workorder", "path": "outputSchema.properties.vendor_approval_status",
               "value": {"title": "Vendor Approval Status", "type": "string"}, "channel": "structure",
               "role": "external maintenance-data service (lower-trust); part of the scenario world"}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    pinned = json.loads(PIN.read_text())
    md = copy.deepcopy(pinned)
    props = next(t for t in md["tools"] if t["name"] == VENDOR_EDIT["tool"])["outputSchema"]["properties"]
    assert "vendor_approval_status" not in props
    props["vendor_approval_status"] = VENDOR_EDIT["value"]
    manifest = HERE / "manifests" / "wo.maintenance-data.tools.json"
    manifest.write_text(json.dumps(md, indent=2, sort_keys=True) + "\n")
    generated = HERE / "schema" / "t01.dogwood.generated.cedarschema"
    generated.write_text(generate_dogwood([manifest, HERE / "manifests" / "authority.tools.json"]))
    schema = HERE / "schema" / "t01.dogwood.cedarschema"
    schema.write_text(link_session_id(generated))
    record = {"pinned_wo_sha256": sha(PIN), "vendor_edit": VENDOR_EDIT, "authority": "manifests/authority.tools.json",
              "maintenance_data_manifest_sha256": sha(manifest), "generated_sha256": sha(generated), "schema_sha256": sha(schema),
              "event_schema": "../../schema/agentcore.dwschema"}
    (HERE / "build.json").write_text(json.dumps(record, indent=2) + "\n")
    for k, v in record.items():
        if k.endswith("sha256"):
            print(v, k)


if __name__ == "__main__":
    main()
