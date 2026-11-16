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


@pytest.mark.skipif(shutil.which("cedar") is None, reason="cedar CLI not on PATH")
def test_link_refuses_a_shared_namespace(tmp_path):
    with pytest.raises(schemagen.SchemaGenError, match="namespace"):
        schemagen.link(S / "trusted.cedarschema", S / "trusted.cedarschema")


# ---------------------------------------------------------------- Dogwood profile (temporal track)

pydogwood = pytest.importorskip("pydogwood", reason="pydogwood not installed (uv group `dogwood`)")


def test_generate_dogwood_reproduces_the_pinned_dogwood_schema():
    assert schemagen.generate_dogwood([DOMAIN / "manifests" / "wo.tools.json"]) == \
        (S / "wo.dogwood.generated.cedarschema").read_text()


def test_dogwood_profile_differs_from_the_cedar_profile_exactly_as_the_ledger_says():
    """transfer-fidelity.md entries 3 and 4: outputs emitted, JSON number -> decimal; Cedar profile has neither."""
    dogwood, cedar = (S / "wo.dogwood.generated.cedarschema").read_text(), (S / "wo.generated.cedarschema").read_text()
    assert "output?: close_workorderOutput" in dogwood and "actual_hours?: decimal" in dogwood
    assert "typeChoice0?: Drupe::close_workorder_Output_WorkOrderMutationResult" in dogwood  # opaque union branch
    assert "output" not in cedar and "actual_hours?: AOB::Number" in cedar
    assert 'action "close_workorder" in [Action::"CallTool"]' in dogwood and "namespace Drupe" in dogwood


def test_cedar_track_config_is_untouched():
    assert schemagen.CONFIG == {"includeOutputs": False, "objectsAsRecords": False, "eraseAnnotations": True,
                                "flattenNamespaces": False, "numbersAsDecimal": False, "deduplicateEntityTypes": False}
    assert schemagen.DOGWOOD_PROFILE == {"include_outputs": True, "encode_numbers_as_decimal": True,
                                         "flatten_namespaces": True}


def test_generate_dogwood_refuses_colliding_tool_names():
    m = DOMAIN / "manifests" / "wo.tools.json"
    with pytest.raises(schemagen.SchemaGenError, match="collide"):
        schemagen.generate_dogwood([m, m])
