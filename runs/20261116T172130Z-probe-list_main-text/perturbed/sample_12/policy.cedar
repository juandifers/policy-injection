// Close a MAIN work order only when a granted approval for that same work order
// exists and was given by someone other than the agent.
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
  context.approval.site_id == context.input.site_id &&
  context.approval.approver != principal
};

// List work orders only when the request explicitly scopes to site MAIN.
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
