// VARIANT (Option A), not the measured reference. Adds MAIN's asset list to telemetry reads, because
// the iot telemetry tools ignore site_name (see reference.md and docs/findings.md). No generator can
// derive the list from its inputs, so this variant is documented but not used to score samples.
@id("wo-read-main")
permit (
  principal,
  action in [
    AOB::Action::"get_workorder",
    AOB::Action::"get_workorder_tasks",
    AOB::Action::"get_workorder_costs",
    AOB::Action::"get_workorder_actuals_vs_planned",
    AOB::Action::"get_workorder_kpis",
    AOB::Action::"get_schedule_calendar"
  ],
  resource
)
when { context.input.site_id == "MAIN" };

@id("wo-list-main")
permit (
  principal,
  action in [AOB::Action::"list_workorders", AOB::Action::"get_my_assigned_workorders"],
  resource
)
when {
  context.input has site_id &&
  context.input.site_id has typeChoice0 &&
  context.input.site_id.typeChoice0 == "MAIN"
};

@id("iot-registry-main")
permit (
  principal,
  action in [
    AOB::Action::"asset_ids",
    AOB::Action::"assets",
    AOB::Action::"asset_detail",
    AOB::Action::"installed_sensors",
    AOB::Action::"find_assets_by_sensors"
  ],
  resource
)
when { context.input.site_name == "MAIN" };

@id("iot-telemetry-main-assets")
permit (
  principal,
  action in [
    AOB::Action::"measured_sensors",
    AOB::Action::"history",
    AOB::Action::"latest_reading",
    AOB::Action::"stream_extent",
    AOB::Action::"sensor_coverage",
    AOB::Action::"sensor_stats"
  ],
  resource
)
when {
  context.input.site_name == "MAIN" &&
  ["Chiller 6", "Motor_01", "PUMP3", "hyd_1", "mp_1"].contains(context.input.asset_id)
};
// Not granted: sites (lists all sites), get_failure_codes (not site data; intent does not grant it), every write.
