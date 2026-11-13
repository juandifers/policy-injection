// Permit opening new work orders, only at site MAIN.
permit (
    principal is AOB::User,
    action == AOB::Action::"generate_work_order",
    resource is AOB::McpServer
)
when {
    context.input.site_id == "MAIN"
};

// Approval and cancellation always stay with people.
forbid (
    principal is AOB::User,
    action == AOB::Action::"approve_workorder",
    resource is AOB::McpServer
);

forbid (
    principal is AOB::User,
    action == AOB::Action::"cancel_workorder",
    resource is AOB::McpServer
);

// Existing work orders must not be changed, assigned or closed by the agent.
forbid (
    principal is AOB::User,
    action == AOB::Action::"update_workorder",
    resource is AOB::McpServer
);

forbid (
    principal is AOB::User,
    action == AOB::Action::"assign_technician",
    resource is AOB::McpServer
);

forbid (
    principal is AOB::User,
    action == AOB::Action::"close_workorder",
    resource is AOB::McpServer
);
