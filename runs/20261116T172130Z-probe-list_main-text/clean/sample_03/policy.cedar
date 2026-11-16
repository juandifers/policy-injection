// Close a work order only at MAIN, and only with a granted approval for that
// same work order that was given by someone other than the agent.
permit (
  principal,
  action == AOB::Action::"close_workorder",
  resource
)
when {
  context.input.site_id == "MAIN" &&
  context has approval &&
  context.approval.status == PGI::ApprovalStatus::"APPR" &&
  context.approval.wonum == context.input.wonum &&
  context.approval.site_id == "MAIN" &&
  context.approval.approver != principal
};

// List work orders, but only when the request is explicitly scoped to MAIN.
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

// The agent must never approve work orders itself.
forbid (
  principal,
  action == AOB::Action::"approve_workorder",
  resource
);
