// Close a work order only at MAIN, and only with a granted approval that
// is for the same work order and was given by someone other than the agent.
permit (
  principal is AOB::User,
  action == AOB::Action::"close_workorder",
  resource is AOB::McpServer
)
when {
  context has approval &&
  context.input.site_id == "MAIN" &&
  context.approval.site_id == context.input.site_id &&
  context.approval.wonum == context.input.wonum &&
  context.approval.status == PGI::ApprovalStatus::"APPR" &&
  context.approval.approver != principal
};

// List work orders only when the request explicitly names MAIN as the site.
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

// The agent must never approve work orders itself.
forbid (
  principal,
  action == AOB::Action::"approve_workorder",
  resource
);
