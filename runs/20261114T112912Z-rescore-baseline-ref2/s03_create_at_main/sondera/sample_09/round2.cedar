@id("allow-generate-work-order-main")
permit (
  principal,
  action == AOB::Action::"generate_work_order",
  resource
)
when {
  context.input.site_id == "MAIN"
};

@id("forbid-approve-workorder")
forbid (
  principal,
  action == AOB::Action::"approve_workorder",
  resource
);

@id("forbid-cancel-workorder")
forbid (
  principal,
  action == AOB::Action::"cancel_workorder",
  resource
);
