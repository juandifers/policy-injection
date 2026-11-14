@id("allow_generate_work_order_main_only")
permit (
  principal,
  action == Action::"generate_work_order",
  resource
)
when {
  context.input.site_id == "MAIN"
};

@id("forbid_approve_workorder")
forbid (
  principal,
  action == Action::"approve_workorder",
  resource
);

@id("forbid_cancel_workorder")
forbid (
  principal,
  action == Action::"cancel_workorder",
  resource
);
