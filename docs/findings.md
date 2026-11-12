# Findings

Results only, each traced to a `runs/<id>/` folder and labeled with the oracle that backs it (enumeration or symcc).
Keep baseline over-permission (no attacker) apart from attack-induced expansion.

_No experimental findings yet. The oracle is validated on the toy scenario only (see `tests/test_oracle.py`); that is a test, not a finding._

## Reconnaissance: AssetOpsBench data and tools (2026-11-12)

Not experiments, so no run id. Reproduce with AssetOpsBench at commit `8941acc` (see `decisions.md`) and
`uv run --project $AOB_DIR python domains/assetopsbench/scripts/aob_mcp.py explore`
(direct MCP stdio calls with `AOB_READONLY=1`; no LLM, no agent runner, no write tool called).

### Sites

`iot.sites` returns **two sites: `MAIN` and `NORTH`**. Both have work orders, so site scoping in our scenarios can use real data. A synthetic site is not needed.

### Work orders

The work-order data is tiny: **3 work orders in total**. Every data manifest (`default`, `scenario_1..3`) loads the same `shared/work_order/workorders.csv`. CouchDB holds 7 docs in `workorder`, which are those 3 plus 4 design docs, so the tool is not hiding any.

| wonum | siteid | status | assetnum | description (truncated) |
|---|---|---|---|---|
| `1000045` | MAIN | WAPPR | CHILLER6 | Investigate anomaly on Chiller 6 condenser water f… |
| `1000046` | MAIN | APPR | PUMP3 | Bearing wear failure mode on Pump 3 - corrective a… |
| `1000050` | NORTH | COMP | AHU2 | Quarterly preventive maintenance - AHU 2 |

- Status values present: **WAPPR, APPR, COMP** (one each). The server code also writes `CAN` (cancel) and recognises the pseudo-filters `OPEN` / `APPROVED_PENDING`.
- wonums are numeric strings (`"1000045"`), not `WO1`-style.
- Field naming differs between data and tools. Stored documents use `siteid`, but every tool parameter is named `site_id`.
- Consequence: universes over real IDs can draw on only 3 wonums and 2 sites. Cases that need a second work order at one site (like toy c3) have to pair `1000045` and `1000046` at MAIN, the only site with two.

### Tools

Classification is empirical. A tool is a **write** if it disappears when the server starts with `AOB_READONLY=1`, and this matches `_READ_TOOLS` / `_WRITE_TOOLS` in `servers/wo/main.py`. iot has no `AOB_READONLY` switch and no database writes in its source.

**wo: 15 tools (9 read, 6 write)**

| read | write |
|---|---|
| `list_workorders`, `get_workorder`, `get_workorder_tasks`, `get_workorder_costs`, `get_workorder_actuals_vs_planned`, `get_workorder_kpis`, `get_schedule_calendar`, `get_my_assigned_workorders`, `get_failure_codes` | `generate_work_order`, `update_workorder`, `approve_workorder`, `assign_technician`, `close_workorder`, `cancel_workorder` |

**iot: 12 tools, all read**: `sites`, `asset_ids`, `asset_detail`, `assets`, `find_assets_by_sensors`, `measured_sensors`, `installed_sensors`, `stream_extent`, `history`, `latest_reading`, `sensor_coverage`, `sensor_stats`.

### Server behaviour that matters for the gate later

- **Errors come back as normal results.** With CouchDB misconfigured, `iot.sites` returned `{"result": {"error": "the data source does not exist …"}}` with `isError=False`. A client that trusts `isError` treats the failure as data. Same lesson as the oracle: errors must be detected explicitly.
- Only `get_failure_codes` carries MCP `ToolAnnotations` (`readOnlyHint=True`). **No write tool declares `readOnlyHint=False` or `destructiveHint`.** The manifest itself does not say which tools mutate state.
