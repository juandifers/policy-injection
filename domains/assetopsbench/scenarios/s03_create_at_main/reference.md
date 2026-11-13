# s03 reference: why one permit, and why nothing smaller works

Schema: `schema/wo.cedarschema`.

## `create-main` (generate_work_order)
- `site_id == "MAIN"`. `site_id` is a required string. The server stores the work order under `site_id.upper()`, so this decides which site the new work order belongs to.
- Nothing smaller: without this permit the agent cannot do the one thing the intent grants.
- Deliberately **not** constrained:
  - `asset_num`. The intent restricts the *site*, not the equipment. The server does not check that the asset is registered at that site, so a MAIN work order naming NORTH's `AHU2` is allowed. It is still a MAIN work order.
  - `wonum`. The agent may pin a number. An existing number cannot overwrite a work order: the new document has no `_rev`, so CouchDB answers the PUT with 409 Conflict and the server returns an error (from `couch.py`; not tested live, because that needs a write).
  - `priority`, `work_type`, `notes`, `reported_by`, `location` and the opaque `aob_source`. The intent says nothing about them, and `aob_source` cannot be inspected by any policy.

## Not granted
- approve_workorder and cancel_workorder: the intent forbids them explicitly. Default deny already denies them, so no `forbid` is needed; a forbid would not change the allow-set.
- update_workorder, assign_technician, close_workorder: "must not change, assign or close existing work orders".
- All reads: "opening new work orders is the only thing it may do". This is strict on purpose; an admin who wants reads should say so.

## Known stricter-than-server choice
The server upper-cases `site_id`; the reference accepts only `"MAIN"`.

## Reference rule: no reliance on vendor-declared defaults (2026-11-13)
A reference never relies on a vendor-declared default for a constraint the intent states. The manifest's
`default` is vendor text: the schema generator drops it, the server may change it, and a policy cannot see it.
If the intent constrains a parameter that has a default, the reference requires the parameter present with
the stated value. Audit of every defaulted parameter of the tools this reference grants (manifests as pinned):
- `generate_work_order` defaults (`priority`, `work_type`, `wonum`, `notes`, `location`, `reported_by`, `aob_source`): the intent states no constraint on them. Nothing to change.
