// Work-order lookups where site_id is a required string: must be MAIN
permit (
  principal is AOB::User,
  action in [
    AOB::Action::"get_workorder",
    AOB::Action::"get_workorder_tasks",
    AOB::Action::"get_workorder_costs",
    AOB::Action::"get_workorder_actuals_vs_planned",
    AOB::Action::"get_workorder_kpis",
    AOB::Action::"get_schedule_calendar"
  ],
  resource is AOB::McpServer
)
when {
  context.input.site_id == "MAIN"
};

// Listing work orders: the site filter must be present and set to MAIN
permit (
  principal is AOB::User,
  action == AOB::Action::"list_workorders",
  resource is AOB::McpServer
)
when {
  context.input has site_id &&
  context.input.site_id has typeChoice0 &&
  context.input.site_id.typeChoice0 == "MAIN"
};

// Open work orders assigned to a technician: site must be MAIN and open_only must be true
permit (
  principal is AOB::User,
  action == AOB::Action::"get_my_assigned_workorders",
  resource is AOB::McpServer
)
when {
  context.input has site_id &&
  context.input.site_id has typeChoice0 &&
  context.input.site_id.typeChoice0 == "MAIN" &&
  context.input has open_only &&
  context.input.open_only == true
};

// Equipment lookups and sensor data reads: site_name must be MAIN
permit (
  principal is AOB::User,
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
  resource is AOB::McpServer
)
when {
  context.input.site_name == "MAIN"
};
