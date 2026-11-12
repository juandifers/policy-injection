@id("read-main")
permit (principal, action == AOB::Action::"list_workorders", resource)
when {
  context.input has site_id &&
  context.input.site_id has typeChoice0 &&
  context.input.site_id.typeChoice0 == "MAIN"
};

@id("close-after-approval")
permit (principal, action == AOB::Action::"close_workorder", resource)
when {
  context.input.site_id == "MAIN" &&
  context has approval &&
  context.approval.wonum == context.input.wonum &&
  context.approval.approver != principal
};
// No permit for approve_workorder: default deny.
// site_id on list_workorders is optional (absent = all sites), so read-main requires it present.
