@id("read-main")
permit (principal, action == AOB::Action::"list_work_orders", resource)
when { context.input.siteid == "MAIN" };

@id("close-after-approval")
permit (principal, action == AOB::Action::"close_work_order", resource)
when {
  context.input.siteid == "MAIN" &&
  context has approval &&
  context.approval.wonum == context.input.wonum &&
  context.approval.approver != principal
};
// No permit for approve_work_order: default deny.
