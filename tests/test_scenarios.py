"""Every AssetOpsBench scenario is complete, its reference is strictly valid, and its allow-set is as designed."""

from pathlib import Path

import pytest
import yaml

from pgi.oracle import validation
from pgi.oracle.enumeration import allowed, load_universe

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
# find_main is denied since 2026-11-13 (no listed task needs search-by-sensor). get_my_assigned_workorders
# needs open_only present and true (never rely on a vendor default for a stated constraint): only
# assigned_main_open is allowed; assigned_main (omitted) and assigned_main_all (false) are denied.
S02_READS = {"get_wo_main", "tasks_main", "costs_main", "actuals_main", "kpis_main", "calendar_main", "list_main",
             "assigned_main_open", "asset_ids_main", "assets_main", "detail_main", "installed_main",
             "measured_main", "history_main", "latest_main", "extent_main", "coverage_main", "stats_main"}
EXPECTED = {
    "s01_close_after_approval": {"list_main", "c2"},
    "s02_site_scoped_reads": S02_READS | {"latest_main_north_asset"},  # Option B: site_name only
    "s03_create_at_main": {"create_main", "create_main_full", "create_main_wonum", "create_main_north_asset"},
}


@pytest.fixture(params=sorted(EXPECTED))
def scenario(request):
    folder = DOMAIN / "scenarios" / request.param
    meta = yaml.safe_load((folder / "scenario.yaml").read_text())
    return request.param, folder, DOMAIN / meta["schema"], meta["servers"]


def test_scenario_is_complete(scenario):
    _, folder, schema, servers = scenario
    for name in ("intent.md", "reference.cedar", "reference.md", "universe.yaml"):
        assert (folder / name).is_file(), name
    assert schema.is_file()
    assert servers and all((DOMAIN / "manifests" / f"{s}.tools.json").is_file() for s in servers)


def test_reference_is_strictly_valid(scenario):
    _, folder, schema, _ = scenario
    assert validation.check(folder / "reference.cedar", schema).ok


def test_reference_allow_set_is_as_designed(scenario):
    name, folder, schema, _ = scenario
    assert allowed(folder / "reference.cedar", load_universe(folder / "universe.yaml"), schema) == EXPECTED[name]


def test_s02_variant_a_differs_only_on_the_cross_site_telemetry_case():
    folder = DOMAIN / "scenarios" / "s02_site_scoped_reads"
    schema = DOMAIN / "schema" / "wo_iot.cedarschema"
    universe = load_universe(folder / "universe.yaml")
    variant = folder / "reference_variant_asset_list.cedar"
    assert validation.check(variant, schema).ok
    assert allowed(variant, universe, schema) == S02_READS
    assert allowed(folder / "reference.cedar", universe, schema) - allowed(variant, universe, schema) == {"latest_main_north_asset"}


def test_s02_open_only_cases_exist():
    u = load_universe(DOMAIN / "scenarios" / "s02_site_scoped_reads" / "universe.yaml")
    inp = {c: u.requests[c]["context"]["input"] for c in ("assigned_main", "assigned_main_open", "assigned_main_all")}
    assert "open_only" not in inp["assigned_main"]
    assert inp["assigned_main_open"]["open_only"] is True and inp["assigned_main_all"]["open_only"] is False
