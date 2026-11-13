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
  context.approval.site_id == context.input.site_id &&
  context.approval.approver != principal
};

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
