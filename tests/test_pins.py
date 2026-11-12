"""Pinned clean inputs must never change. Hashes are recorded in docs/decisions.md."""

import hashlib
from pathlib import Path

import pytest

MANIFESTS = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench" / "manifests"
PINNED = {
    "wo.tools.json": "343611eceeda99e0148b96a87a47879ed074a0fe90bcad64b07428f88a0907e6",
    "iot.tools.json": "50a3c21bbda8663f979ac45d9df69619e37f7d990ca9ed46e596d029656668d4",
}


@pytest.mark.parametrize("name", sorted(PINNED))
def test_manifest_is_pinned(name):
    assert hashlib.sha256((MANIFESTS / name).read_bytes()).hexdigest() == PINNED[name]
