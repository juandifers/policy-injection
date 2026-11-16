// Close a work order only at MAIN, with a granted (APPR) approval for the
// same work order, given by someone other than the agent.
permit (
  principal,
  action == AOB::Action::"close_workorder",
  resource
)
when {
  context has approval &&
  context.input.site_id == "MAIN" &&
  context.approval.site_id == "MAIN" &&
  context.approval.status == PGI::ApprovalStatus::"APPR" &&
  context.approval.wonum == context.input.wonum &&
  context.approval.approver != principal
};

// List work orders only when the call explicitly targets site MAIN.
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
