// Work-order lookups where site_id is a required argument: only MAIN.
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
when {
  context.input.site_id == "MAIN"
};

// Listing work orders: site_id is optional, so it must be present and be MAIN.
permit (
  principal,
  action == AOB::Action::"list_workorders",
  resource
)
when {
  context.input has site_id &&
  context.input.site_id has typeChoice0 &&
  context.input.site_id.typeChoice0 == "MAIN"
};

// Open work orders assigned to a technician: site_id must be MAIN, and only open ones.
permit (
  principal,
  action == AOB::Action::"get_my_assigned_workorders",
  resource
)
when {
  context.input has site_id &&
  context.input.site_id has typeChoice0 &&
  context.input.site_id.typeChoice0 == "MAIN" &&
  (!(context.input has open_only) || context.input.open_only == true)
};

// Equipment and sensor-data lookups: only for the MAIN site.
permit (
  principal,
  action in [
    AOB::Action::"asset_ids",
    AOB::Action::"assets",
    AOB::Action::"asset_detail",
    AOB::Action::"installed_sensors",
    AOB::Action::"history",
    AOB::Action::"latest_reading",
    AOB::Action::"sensor_coverage",
    AOB::Action::"sensor_stats"
  ],
  resource
)
when {
  context.input.site_name == "MAIN"
};
