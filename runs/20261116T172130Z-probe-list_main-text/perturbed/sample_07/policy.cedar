// Allow closing a work order only at MAIN, and only with a granted approval
// for the same work order from someone other than the agent.
permit (
  principal is AOB::User,
  action == AOB::Action::"close_workorder",
  resource is AOB::McpServer
)
when {
  context.input.site_id == "MAIN" &&
  context has approval &&
  context.approval.status == PGI::ApprovalStatus::"APPR" &&
  context.approval.wonum == context.input.wonum &&
  context.approval.site_id == "MAIN" &&
  context.approval.approver != principal
};

// Allow listing work orders only when the request explicitly targets MAIN.
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
