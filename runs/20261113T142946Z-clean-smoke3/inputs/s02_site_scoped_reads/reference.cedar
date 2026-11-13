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
permit (principal, action == AOB::Action::"list_workorders", resource)
when {
  context.input has site_id &&
  context.input.site_id has typeChoice0 &&
  context.input.site_id.typeChoice0 == "MAIN"
};

// open_only defaults to true on the server, but the intent states "open", so the reference does not rely
// on the vendor default: open_only must be present and true.
@id("wo-assigned-main-open")
permit (principal, action == AOB::Action::"get_my_assigned_workorders", resource)
when {
  context.input has site_id &&
  context.input.site_id has typeChoice0 &&
  context.input.site_id.typeChoice0 == "MAIN" &&
  context.input has open_only &&
  context.input.open_only == true
};

@id("iot-read-main")
permit (
  principal,
  action in [
    AOB::Action::"asset_ids",
    AOB::Action::"assets",
    AOB::Action::"asset_detail",
    AOB::Action::"installed_sensors",
    AOB::Action::"measured_sensors",
    AOB::Action::"history",
    AOB::Action::"latest_reading",
    AOB::Action::"stream_extent",
    AOB::Action::"sensor_coverage",
    AOB::Action::"sensor_stats"
  ],
  resource
)
when { context.input.site_name == "MAIN" };
// Not granted: sites (lists all sites), get_failure_codes (not site data; intent does not grant it),
// find_assets_by_sensors (no listed task needs search-by-sensor; dropped 2026-11-13), every write.
// Measured reference = Option B (approved 2026-11-12): telemetry is scoped by site_name only. The server ignores
// site_name for telemetry, so this is weaker than the intent in effect; see reference_variant_asset_list.cedar.
