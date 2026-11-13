// Read-only, MAIN-only access for the maintenance agent.

// Work orders: site_id is required and must be MAIN.
@id("wo-read-main-required-site")
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

// Work order lists: site_id is optional in the tool, so it must be present and equal MAIN.
// An absent site_id would list across all sites and is therefore denied.
@id("wo-read-main-optional-site")
permit (
    principal,
    action in [
        AOB::Action::"list_workorders",
        AOB::Action::"get_my_assigned_workorders"
    ],
    resource
)
when {
    context.input has site_id &&
    context.input.site_id has typeChoice0 &&
    context.input.site_id.typeChoice0 == "MAIN"
};

// Equipment and sensor data: site_name is required and must be MAIN.
@id("iot-read-main")
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

// Explicit denials: no writes, and no cross-site listing.
@id("deny-mutations-and-cross-site")
forbid (
    principal,
    action in [
        AOB::Action::"approve_workorder",
        AOB::Action::"assign_technician",
        AOB::Action::"close_workorder",
        AOB::Action::"cancel_workorder",
        AOB::Action::"generate_work_order",
        AOB::Action::"update_workorder",
        AOB::Action::"sites"
    ],
    resource
);
