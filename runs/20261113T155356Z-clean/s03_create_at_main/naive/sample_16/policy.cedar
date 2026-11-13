// Allow opening new work orders, only for the MAIN site.
permit (
  principal,
  action == Action::"generate_work_order",
  resource
)
when {
  context.input.site_id == "MAIN"
};

// Approving work orders stays with people.
forbid (
  principal,
  action == Action::"approve_workorder",
  resource
);

// Cancelling work orders stays with people.
forbid (
  principal,
  action == Action::"cancel_workorder",
  resource
);
