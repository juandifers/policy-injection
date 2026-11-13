// Read-only MAIN access for the maintenance agent.

// 1. Work orders at MAIN, addressed by a required site_id.
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

// 2. Work order listing, where site_id is optional and must be explicitly MAIN.
//    An omitted or null site_id would list across all sites, so it is not permitted.
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

// 3. Work orders assigned to a technician, limited to MAIN and to open work orders.
//    The site must be explicit, and open_only must be explicitly true.
permit (
    principal,
    action == AOB::Action::"get_my_assigned_workorders",
    resource
)
when {
    context.input has site_id &&
    context.input.site_id has typeChoice0 &&
    context.input.site_id.typeChoice0 == "MAIN" &&
    context.input has open_only &&
    context.input.open_only == true
};

// 4. MAIN equipment registry and sensor data, addressed by site_name.
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
        AOB::Action::"sensor_coverage",
        AOB::Action::"sensor_stats",
        AOB::Action::"stream_extent"
    ],
    resource
)
when {
    context.input.site_name == "MAIN"
};

// 5. Defense in depth: no site-addressed read may name another site.
forbid (
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
    context.input.site_id != "MAIN"
};

forbid (
    principal,
    action in [
        AOB::Action::"asset_ids",
        AOB::Action::"assets",
        AOB::Action::"asset_detail",
        AOB::Action::"installed_sensors",
        AOB::Action::"measured_sensors",
        AOB::Action::"history",
        AOB::Action::"latest_reading",
        AOB::Action::"sensor_coverage",
        AOB::Action::"sensor_stats",
        AOB::Action::"stream_extent"
    ],
    resource
)
when {
    context.input.site_name != "MAIN"
};

// 6. Never allow cross-site enumeration, even if a permit is added later.
forbid (
    principal,
    action == AOB::Action::"sites",
    resource
);

// 7. Never allow any write or workflow action.
forbid (
    principal,
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
