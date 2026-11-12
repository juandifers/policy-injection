"""Pinned clean inputs must never change. Hashes are recorded in docs/decisions.md."""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
PINNED = {
    "manifests/wo.tools.json": "343611eceeda99e0148b96a87a47879ed074a0fe90bcad64b07428f88a0907e6",
    "manifests/iot.tools.json": "50a3c21bbda8663f979ac45d9df69619e37f7d990ca9ed46e596d029656668d4",
    # Generator output, byte-for-byte as cedar-policy-mcp-schema-generator 0.7.0 wrote it.
    "schema/wo.generated.cedarschema": "ca4e73eb1c36f6e04dc10c8607af35a546d3cb9c348b0095db05810dcbf7aae5",
    "schema/iot.generated.cedarschema": "b5defb2c55127b4cfa7352b5b336f0f2e5fda7576db467809581da6eaf85897b",
}


@pytest.mark.parametrize("name", sorted(PINNED))
def test_file_is_pinned(name):
    assert hashlib.sha256((DOMAIN / name).read_bytes()).hexdigest() == PINNED[name]


@pytest.mark.skipif(shutil.which("cedar") is None, reason="cedar CLI not on PATH")
def test_final_schema_is_exactly_generated_plus_trusted():
    """wo.cedarschema must equal link(wo.generated, trusted); nobody edits it by hand."""
    s = DOMAIN / "schema"
    proc = subprocess.run([sys.executable, str(DOMAIN / "scripts" / "link_schema.py"), str(s / "wo.generated.cedarschema"),
                           str(s / "trusted.cedarschema"), str(s / "wo.cedarschema"), "--check"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
