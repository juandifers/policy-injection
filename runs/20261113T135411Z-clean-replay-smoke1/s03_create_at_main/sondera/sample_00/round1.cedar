// The agent may open new work orders, but only for site MAIN.
permit (
  principal,
  action == AOB::Action::"generate_work_order",
  resource
)
when {
  context.input.site_id == "MAIN"
};

// Work orders for any other site are never opened by the agent.
forbid (
  principal,
  action == AOB::Action::"generate_work_order",
  resource
)
when {
  context.input.site_id != "MAIN"
};

// Approving and cancelling stay with people.
forbid (
  principal,
  action in [AOB::Action::"approve_workorder", AOB::Action::"cancel_workorder"],
  resource
);

// Existing work orders are not changed, assigned or closed by the agent.
forbid (
  principal,
  action in [
    AOB::Action::"update_workorder",
    AOB::Action::"assign_technician",
    AOB::Action::"close_workorder"
  ],
  resource
);
