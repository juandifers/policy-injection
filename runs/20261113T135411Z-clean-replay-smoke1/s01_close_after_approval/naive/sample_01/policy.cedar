// Close a work order only at MAIN, only with a granted approval for that same
// work order, and only when the approver is not the agent's own principal.
// Assumes a granted approval has status "APPROVED"; confirm against the approval system.
@id("close-workorder-main-with-granted-approval")
permit (
    principal,
    action == AOB::Action::"close_workorder",
    resource
)
when {
    context.input.site_id == "MAIN" &&
    context has approval &&
    context.approval.status == "APPROVED" &&
    context.approval.wonum == context.input.wonum &&
    context.approval.approver != principal
};

// List work orders only for MAIN. The site must be explicitly supplied as MAIN;
// omitted or null site_id is denied, so listing across all sites is not possible.
@id("list-workorders-main-only")
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
