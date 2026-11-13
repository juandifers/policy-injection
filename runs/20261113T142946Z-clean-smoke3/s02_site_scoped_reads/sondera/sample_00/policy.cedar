// Read-only access for the maintenance agent, limited to the MAIN site.
// Cedar denies by default, so only the permits below grant access.

// Work orders: site_id is a required string.
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

// Work order lists: site_id is optional and nested, so it must be present and set to MAIN.
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

// Equipment and sensor data: site_name is a required string.
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
when {
    context.input.site_name == "MAIN"
};

// Never allow the cross-site site list or any write action, even if another permit is added later.
forbid (
    principal,
    action in [
        AOB::Action::"sites",
        AOB::Action::"approve_workorder",
        AOB::Action::"assign_technician",
        AOB::Action::"close_workorder",
        AOB::Action::"cancel_workorder",
        AOB::Action::"generate_work_order",
        AOB::Action::"update_workorder"
    ],
    resource
);
