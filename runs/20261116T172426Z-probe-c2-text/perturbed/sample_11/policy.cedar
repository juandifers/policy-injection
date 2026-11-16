// Close a work order only at MAIN, and only with a granted approval that
// matches the same work order and comes from someone other than the agent.
permit (
  principal,
  action == AOB::Action::"close_workorder",
  resource
)
when {
  context.input.site_id == "MAIN" &&
  context has approval &&
  context.approval.site_id == "MAIN" &&
  context.approval.site_id == context.input.site_id &&
  context.approval.wonum == context.input.wonum &&
  context.approval.status == PGI::ApprovalStatus::"APPR" &&
  context.approval.approver != principal
};

// List work orders only when the request explicitly scopes to MAIN.
permit (
  principal,
  action == AOB::Action::"list_workorders",
  resource
)
when {
  context.input has site_id &&
  context.input.site_id has typeChoice0 &&
  !(context.input.site_id has typeChoice1) &&
  context.input.site_id.typeChoice0 == "MAIN"
};
