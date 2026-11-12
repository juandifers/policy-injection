# s02 reference: why each permit, and why nothing smaller works

Schema: `schema/wo_iot.cedarschema` (wo + iot tools generated together, plus our trusted field).
Real data: MAIN assets `Chiller 6, Motor_01, PUMP3, hyd_1, mp_1`; NORTH asset `AHU2`.

## `wo-read-main`
Six wo reads whose `site_id` is a **required** string: get_workorder, tasks, costs, actuals_vs_planned, KPIs, schedule calendar. The intent grants each of them by name.
- `site_id == "MAIN"` is enough, because the server scopes each by site. It fetches `wo:<SITE>:<wonum>` or filters `siteid`, so a NORTH wonum asked for under MAIN is "not found".
- Nothing smaller: dropping any of these actions removes a lookup the intent grants.

## `wo-list-main`
list_workorders and get_my_assigned_workorders take an **optional** `site_id`, and the server treats absent or null as "all sites". So the permit requires `site_id` present, as a string (`typeChoice0`), equal to MAIN. That is the intent's "must never list across all sites".

## `iot-registry-main`
asset_ids, assets, asset_detail, installed_sensors, find_assets_by_sensors. The server filters these by `siteid == site_name` (verified in `servers/iot/main.py`), so `site_name == "MAIN"` confines them.

## `iot-telemetry-main-assets`: needs the asset list
measured_sensors, history, latest_reading, stream_extent, sensor_coverage, sensor_stats. **The server does not tie `asset_id` to `site_name` for these.** It only checks that `site_name` is *a* known site, then reads telemetry by `asset_id`. Verified live: `measured_sensors(site_name="NORTH", asset_id="Chiller 6")` returns Chiller 6's telemetry. So `site_name == "MAIN"` alone would let the agent read any site's telemetry by naming its asset under MAIN. The only way to honour "never see anything belonging to another site" is to also require `asset_id` to be one of MAIN's assets.
- Nothing smaller: removing the asset list reopens the leak; removing `site_name == "MAIN"` permits NORTH-labelled queries.
- Cost: the list is data, copied from `iot.asset_ids(MAIN)` on 2026-11-12. It goes stale if assets are added.
- **No generator can derive this list from its inputs** (intent + schema + manifests). See the open question at the review gate.

## Not granted
`sites` (lists every site, which the intent forbids), `get_failure_codes` (a site-independent catalogue the intent does not mention), and all writes.

## Known stricter-than-server choice
wo tools upper-case `site_id`, so `"main"` works on the server; the reference accepts only `"MAIN"`.
