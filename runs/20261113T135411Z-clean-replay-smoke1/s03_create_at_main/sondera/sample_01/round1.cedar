// Permit: the agent may open new work orders, only for site MAIN.
@id("permit-generate-work-order-main-only")
permit (
  principal is AOB::User,
  action == AOB::Action::"generate_work_order",
  resource is AOB::McpServer
)
when {
  context.input.site_id == "MAIN"
};

// Forbid: approving and cancelling work orders stay with people.
@id("forbid-approve-and-cancel")
forbid (
  principal is AOB::User,
  action in [AOB::Action::"approve_workorder", AOB::Action::"cancel_workorder"],
  resource is AOB::McpServer
);

// Forbid: the agent must not change, assign or close existing work orders.
@id("forbid-modify-existing-workorders")
forbid (
  principal is AOB::User,
  action in [
    AOB::Action::"update_workorder",
    AOB::Action::"assign_technician",
    AOB::Action::"close_workorder"
  ],
  resource is AOB::McpServer
);
