// Close a work order only at MAIN, and only with a granted approval that
// names this same work order and was given by someone other than the agent.
//
// "APPR" is the status the approve_workorder tool sets (-> APPR). The exact
// match excludes the waiting state (WAPPR) and APPROVED_PENDING. Confirm the
// approval record's status value against the approval system before deploying.
//
// The approval schema has no site field, so it is matched on wonum only.
// Confirm that wonum numbers are unique across sites, or that the approval
// system scopes approvals by site, before relying on this match.
@id("close-workorder-main-with-granted-approval")
permit (
    principal is AOB::User,
    action == AOB::Action::"close_workorder",
    resource is AOB::McpServer
)
when {
    context.input.site_id == "MAIN" &&
    context has approval &&
    context.approval.status == "APPR" &&
    context.approval.wonum == context.input.wonum &&
    context.approval.approver != principal
};

// List work orders only when site_id is explicitly MAIN. An omitted or null
// site_id does not match, so listing across all sites is not allowed.
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

// The agent must not approve work orders. This forbid overrides any permit.
@id("forbid-approve-workorder")
forbid (
    principal,
    action == AOB::Action::"approve_workorder",
    resource
);
