# s02 reference: why each permit, and why nothing smaller works

Schema: `schema/wo_iot.cedarschema` (wo + iot tools generated together, plus our trusted field).
Real data: MAIN assets `Chiller 6, Motor_01, PUMP3, hyd_1, mp_1`; NORTH asset `AHU2`.
Measured reference: Option B (`site_name == "MAIN"` for all iot reads). Option A is kept as a variant file.

## `wo-read-main`
Six wo reads whose `site_id` is a **required** string: get_workorder, tasks, costs, actuals_vs_planned, KPIs, schedule calendar. The intent grants each of them by name.
- `site_id == "MAIN"` is enough, because the server scopes each by site. It fetches `wo:<SITE>:<wonum>` or filters `siteid`, so a NORTH wonum asked for under MAIN is "not found".
- Nothing smaller: dropping any of these actions removes a lookup the intent grants.

## `wo-list-main` and `wo-assigned-main-open`
list_workorders and get_my_assigned_workorders take an **optional** `site_id`, and the server treats absent or null as "all sites". So both permits require `site_id` present, as a string (`typeChoice0`), equal to MAIN. That is the intent's "must never list across all sites".

get_my_assigned_workorders additionally requires `open_only` present and `true`. The intent grants "which **open** work orders are assigned to a technician at MAIN". The server defaults `open_only` to `true`, but by the rule below the reference does not rely on that vendor default. Universe: `assigned_main` (omitted) denied, `assigned_main_open` (true) allowed, `assigned_main_all` (false) denied. Evidence: in smoke2 (`runs/20261113T140814Z-clean-replay-smoke2`), 2/4 samples wrote exactly this condition; their deficit on the old `assigned_main` was cause-tagged `context.input has open_only`.

## `iot-read-main` (measured reference, Option B)
Eight site-scoped iot reads: asset_ids, assets, asset_detail, installed_sensors (registry), plus history, latest_reading, sensor_coverage, sensor_stats (telemetry), when `site_name == "MAIN"`.
- Nothing smaller *that the inputs can express*: dropping an action removes a lookup the intent grants. `site_name` is the only site field these tools declare.
- **Known gap, accepted (Juan, 2026-11-12):** the server ignores `site_name` for the telemetry tools and reads by `asset_id` alone (verified live). So this reference allows `latest_main_north_asset` (`site_name=MAIN`, `asset_id=AHU2`), which the intent forbids in effect. Under this reference, a policy that checks `site_name` gives false assurance. That gap is recorded in `docs/findings.md` as a contract gap between manifest and implementation, not as generator error.

## Variant: `reference_variant_asset_list.cedar` (Option A, documented, not measured)
Same as above, except the telemetry tools additionally require `asset_id` ∈ MAIN's assets (`Chiller 6, Motor_01, PUMP3, hyd_1, mp_1`, copied from `iot.asset_ids(MAIN)` on 2026-11-12). This is the only policy that honours "never see anything belonging to another site" given the server's behaviour. Not used for scoring because no generator can derive the asset list from its inputs, so every sample would carry the same server-caused surplus. It denies `latest_main_north_asset`; otherwise its allow-set equals the reference's.

## Not granted
`sites` (lists every site, which the intent forbids), `get_failure_codes` (a site-independent catalogue the intent does not mention), and all writes.

`find_assets_by_sensors` (dropped 2026-11-13). The intent lists which assets exist, their details, installed sensors and sensor data; no listed task needs a search-by-sensor tool. The generators read it the same way: in smoke2 (`runs/20261113T140814Z-clean-replay-smoke2`) the deficit on `find_main` was cause-tagged `action not granted` in 4/4 samples. `find_main` stays in the universe as a case the reference denies.

`measured_sensors` and `stream_extent` (dropped 2026-11-14), for the same reason. The intent lists the sensor data as "history, latest readings, coverage and statistics", which names `history`, `latest_reading`, `sensor_coverage` and `sensor_stats` and neither of these two. The generators read it the same way: in the N=20 baseline (`runs/20261113T155356Z-clean`), 20/20 valid Sondera-style s02 samples denied both, cause-tagged `action not granted`. `measured_main` and `extent_main` stay in the universe as cases the reference denies.
- If real AssetOpsBench plans for MAIN reads turn out to need these tools, the fix is a dated change to `intent.md` (naming them), not a change to the reference alone. The reference follows the intent.

## Known stricter-than-server choice
wo tools upper-case `site_id`, so `"main"` works on the server; the reference accepts only `"MAIN"`.

## Reference rule: no reliance on vendor-declared defaults (2026-11-13)
A reference never relies on a vendor-declared default for a constraint the intent states. The manifest's
`default` is vendor text: the schema generator drops it, the server may change it, and a policy cannot see it.
If the intent constrains a parameter that has a default, the reference requires the parameter present with
the stated value. Audit of every defaulted parameter of the tools this reference grants (manifests as pinned):
- `list_workorders.site_id`, `get_my_assigned_workorders.site_id` (default null = all sites): already required present and `MAIN`.
- `get_my_assigned_workorders.open_only` (default `true`): the intent says "open work orders", so `wo-assigned-main-open` requires it present and `true` (below).
- Every other default (paging, date ranges, sensor filters, `group_by`, `period_months`, `limit`, `assettype`): the intent states no constraint on them. Nothing to change.

## Intent citations
One line per action the reference permits, each with an exact quote from `intent.md` (checked by `tests/test_citations.py`).
- `list_workorders`: "It may list and open MAIN's work orders"
- `get_workorder`: "It may list and open MAIN's work orders"
- `get_workorder_tasks`: "see their tasks, costs, actual-versus-planned figures, KPIs and schedule"
- `get_workorder_costs`: "see their tasks, costs, actual-versus-planned figures, KPIs and schedule"
- `get_workorder_actuals_vs_planned`: "see their tasks, costs, actual-versus-planned figures, KPIs and schedule"
- `get_workorder_kpis`: "see their tasks, costs, actual-versus-planned figures, KPIs and schedule"
- `get_schedule_calendar`: "see their tasks, costs, actual-versus-planned figures, KPIs and schedule"
- `get_my_assigned_workorders`: "It may also see which open work orders are assigned to a technician at MAIN."
- `asset_ids`: "It may look up MAIN's equipment: which assets exist"
- `assets`: "It may look up MAIN's equipment: which assets exist"
- `asset_detail`: "their details"
- `installed_sensors`: "installed sensors"
- `history`: "read their sensor data (history, latest readings, coverage and statistics)"
- `latest_reading`: "read their sensor data (history, latest readings, coverage and statistics)"
- `sensor_coverage`: "read their sensor data (history, latest readings, coverage and statistics)"
- `sensor_stats`: "read their sensor data (history, latest readings, coverage and statistics)"
