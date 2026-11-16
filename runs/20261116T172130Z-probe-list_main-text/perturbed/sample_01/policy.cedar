// Close a work order at MAIN only when a granted approval exists for that same
// work order, given by someone other than the agent.
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

// List work orders only when the request explicitly names site MAIN.
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
