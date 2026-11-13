// Read-only access for the maintenance agent to the MAIN site.
// Every permitted lookup must name MAIN explicitly. Each permit checks the
// site in the request, so nothing is returned for other sites (such as NORTH).

// Work-order reads scoped by a required site_id.
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

// Equipment and sensor reads scoped by a required site_name.
permit (
    principal is AOB::User,
    action in [
        AOB::Action::"asset_ids",
        AOB::Action::"asset_detail",
        AOB::Action::"assets",
        AOB::Action::"installed_sensors",
        AOB::Action::"measured_sensors",
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

// list_workorders: site_id is optional, so it must be present and equal MAIN.
// An omitted site_id would list work orders across all sites and is denied.
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

// get_my_assigned_workorders: site_id must be MAIN, and only open work orders
// are visible. open_only may be omitted (the tool defaults it to true), but an
// explicit false is denied.
permit (
    principal is AOB::User,
    action == AOB::Action::"get_my_assigned_workorders",
    resource is AOB::McpServer
)
when {
    context.input has site_id &&
    context.input.site_id has typeChoice0 &&
    context.input.site_id.typeChoice0 == "MAIN" &&
    (
        (context.input has open_only && context.input.open_only) ||
        !(context.input has open_only)
    )
};

// Defense in depth: no write or state-changing action is ever permitted for this agent.
forbid (
    principal is AOB::User,
    action in [
        AOB::Action::"generate_work_order",
        AOB::Action::"update_workorder",
        AOB::Action::"approve_workorder",
        AOB::Action::"assign_technician",
        AOB::Action::"close_workorder",
        AOB::Action::"cancel_workorder"
    ],
    resource
);

// Not granted (default deny): sites (lists all sites), get_failure_codes (not
// site-scoped), find_assets_by_sensors (not in the granted set), and
// stream_extent (not in the granted set).
