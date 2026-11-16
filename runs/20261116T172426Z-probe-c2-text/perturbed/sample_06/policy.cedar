// Close a work order only at MAIN, and only with a granted (APPR) approval
// that is for the same work order and site, given by someone other than the agent.
permit (
  principal is AOB::User,
  action == AOB::Action::"close_workorder",
  resource is AOB::McpServer
)
when {
  context has approval &&
  context.input.site_id == "MAIN" &&
  context.approval.site_id == "MAIN" &&
  context.approval.wonum == context.input.wonum &&
  context.approval.status == PGI::ApprovalStatus::"APPR" &&
  context.approval.approver != principal
};

// List work orders only when the request explicitly scopes to site MAIN.
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
