// Close a work order only at MAIN, and only with a granted approval
// for that same work order that was given by someone other than the agent.
permit (
  principal,
  action == Action::"close_workorder",
  resource
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
  principal,
  action == Action::"list_workorders",
  resource
)
when {
  context.input has site_id &&
  context.input.site_id has typeChoice0 &&
  context.input.site_id.typeChoice0 == "MAIN"
};

// The agent must never approve work orders itself.
forbid (
  principal,
  action == Action::"approve_workorder",
  resource
);
