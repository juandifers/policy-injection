"""pgi.schemagen reproduces the pinned generated and linked schemas byte-for-byte from the pinned manifests."""

import shutil
from pathlib import Path

import pytest

from pgi import schemagen

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
S = DOMAIN / "schema"
TARGETS = {"wo": ["wo"], "iot": ["iot"], "wo_iot": ["wo", "iot"]}


@pytest.mark.parametrize("target", sorted(TARGETS))
def test_generate_reproduces_the_pinned_generated_schema(target):
    manifests = [DOMAIN / "manifests" / f"{s}.tools.json" for s in TARGETS[target]]
    assert schemagen.generate(S / "stub.cedarschema", manifests) == (S / f"{target}.generated.cedarschema").read_text()


@pytest.mark.skipif(shutil.which("cedar") is None, reason="cedar CLI not on PATH")
@pytest.mark.parametrize("target", ["wo", "wo_iot"])
def test_link_reproduces_the_pinned_final_schema(target):
    assert schemagen.link(S / f"{target}.generated.cedarschema", S / "trusted.cedarschema") == \
        (S / f"{target}.cedarschema").read_text()


def test_colliding_tool_names_are_refused(tmp_path):
    m = DOMAIN / "manifests" / "wo.tools.json"
    with pytest.raises(schemagen.SchemaGenError, match="collide"):
        schemagen.generate(S / "stub.cedarschema", [m, m])


def test_link_refuses_a_shared_namespace(tmp_path):
    with pytest.raises(schemagen.SchemaGenError, match="namespace"):
        schemagen.link(S / "trusted.cedarschema", S / "trusted.cedarschema")
