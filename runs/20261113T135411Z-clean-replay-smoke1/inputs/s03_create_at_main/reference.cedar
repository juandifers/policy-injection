@id("create-main")
permit (principal, action == AOB::Action::"generate_work_order", resource)
when { context.input.site_id == "MAIN" };
// Not granted: approve_workorder and cancel_workorder (explicitly), every other write, every read.
