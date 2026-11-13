// Close a work order only at MAIN, and only with a granted (APPR) approval
// that is for the same work order and was given by someone other than the agent.
permit (
  principal,
  action == AOB::Action::"close_workorder",
  resource
)
when {
  context.input.site_id == "MAIN" &&
  context has approval &&
  context.approval.status == PGI::ApprovalStatus::"APPR" &&
  context.approval.site_id == "MAIN" &&
  context.approval.wonum == context.input.wonum &&
  context.approval.approver != principal
};

// List work orders only when the request explicitly scopes to the MAIN site.
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
