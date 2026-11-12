// Close a work order only at MAIN, and only with a granted approval that
// names this same work order and was given by someone other than the agent.
// Assumes a granted approval has status "APPROVED". Confirm this value
// against the approval system before deploying.
// The approval schema has no site field, so the approval is matched on
// wonum only.
@id("close-workorder-main-with-granted-approval")
permit (
    principal is AOB::User,
    action == AOB::Action::"close_workorder",
    resource is AOB::McpServer
)
when {
    context.input.site_id == "MAIN" &&
    context has approval &&
    context.approval.status == "APPROVED" &&
    context.approval.wonum == context.input.wonum &&
    context.approval.approver != principal
};

// List work orders only when site_id is explicitly MAIN. An omitted or null
// site_id is not matched, so listing across all sites is not allowed.
@id("list-workorders-main-only")
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
