// Close a work order only at MAIN, and only with a granted (APPR) approval
// for that same work order and site, made by someone other than the agent.
permit (
  principal,
  action == AOB::Action::"close_workorder",
  resource
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
  principal,
  action == AOB::Action::"list_workorders",
  resource
)
when {
  context.input has site_id &&
  context.input.site_id has typeChoice0 &&
  context.input.site_id.typeChoice0 == "MAIN" &&
  !(context.input.site_id has typeChoice1)
};
