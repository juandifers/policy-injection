permit (
    principal is AOB::User,
    action == AOB::Action::"generate_work_order",
    resource is AOB::McpServer
)
when {
    context.input.site_id == "MAIN"
};

forbid (
    principal,
    action in [
        AOB::Action::"approve_workorder",
        AOB::Action::"cancel_workorder",
        AOB::Action::"update_workorder",
        AOB::Action::"assign_technician",
        AOB::Action::"close_workorder"
    ],
    resource
);
