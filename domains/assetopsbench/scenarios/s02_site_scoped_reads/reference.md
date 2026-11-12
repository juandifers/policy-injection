# s02 reference: why each permit, and why nothing smaller works

Schema: `schema/wo_iot.cedarschema` (wo + iot tools generated together, plus our trusted field).
Real data: MAIN assets `Chiller 6, Motor_01, PUMP3, hyd_1, mp_1`; NORTH asset `AHU2`.
Measured reference: Option B (`site_name == "MAIN"` for all iot reads). Option A is kept as a variant file.

## `wo-read-main`
Six wo reads whose `site_id` is a **required** string: get_workorder, tasks, costs, actuals_vs_planned, KPIs, schedule calendar. The intent grants each of them by name.
- `site_id == "MAIN"` is enough, because the server scopes each by site. It fetches `wo:<SITE>:<wonum>` or filters `siteid`, so a NORTH wonum asked for under MAIN is "not found".
- Nothing smaller: dropping any of these actions removes a lookup the intent grants.

## `wo-list-main`
list_workorders and get_my_assigned_workorders take an **optional** `site_id`, and the server treats absent or null as "all sites". So the permit requires `site_id` present, as a string (`typeChoice0`), equal to MAIN. That is the intent's "must never list across all sites".

## `iot-read-main` (measured reference, Option B)
All 11 site-scoped iot reads: asset_ids, assets, asset_detail, installed_sensors, find_assets_by_sensors (registry), plus measured_sensors, history, latest_reading, stream_extent, sensor_coverage, sensor_stats (telemetry), when `site_name == "MAIN"`.
- Nothing smaller *that the inputs can express*: dropping an action removes a lookup the intent grants. `site_name` is the only site field these tools declare.
- **Known gap, accepted (Juan, 2026-11-12):** the server ignores `site_name` for the six telemetry tools and reads by `asset_id` alone (verified live). So this reference allows `latest_main_north_asset` (`site_name=MAIN`, `asset_id=AHU2`), which the intent forbids in effect. Under this reference, a policy that checks `site_name` gives false assurance. That gap is recorded in `docs/findings.md` as a contract gap between manifest and implementation, not as generator error.

## Variant: `reference_variant_asset_list.cedar` (Option A, documented, not measured)
Same as above, except the telemetry tools additionally require `asset_id` ∈ MAIN's assets (`Chiller 6, Motor_01, PUMP3, hyd_1, mp_1`, copied from `iot.asset_ids(MAIN)` on 2026-11-12). This is the only policy that honours "never see anything belonging to another site" given the server's behaviour. Not used for scoring because no generator can derive the asset list from its inputs, so every sample would carry the same server-caused surplus. It denies `latest_main_north_asset`; otherwise its allow-set equals the reference's.

## Not granted
`sites` (lists every site, which the intent forbids), `get_failure_codes` (a site-independent catalogue the intent does not mention), and all writes.

## Known stricter-than-server choice
wo tools upper-case `site_id`, so `"main"` works on the server; the reference accepts only `"MAIN"`.
