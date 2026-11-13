@id("allow-generate-work-order-main-only")
permit (
  principal,
  action == Action::"generate_work_order",
  resource
)
when {
  context.input.site_id == "MAIN"
};

@id("forbid-approve-workorder")
forbid (
  principal,
  action == Action::"approve_workorder",
  resource
);

@id("forbid-cancel-workorder")
forbid (
  principal,
  action == Action::"cancel_workorder",
  resource
);
