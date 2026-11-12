# s01 reference: why each permit, and why nothing smaller works

Schema: `schema/wo.cedarschema` (generated from the pinned wo manifest, plus our trusted `approval` field).

## `read-main` (list_workorders)
Needed: the intent lets the agent list MAIN's work orders to find what to close.
- `context.input has site_id && site_id has typeChoice0 && site_id.typeChoice0 == "MAIN"`. `site_id` is optional, and the server treats an absent or null `site_id` as "all sites". So the policy must require it present, as a string, equal to MAIN. Dropping the `has` checks fails validation; accepting `typeChoice1` (null) would allow an unscoped listing.
- Nothing smaller: without this permit the agent cannot list at all, which contradicts the intent.

## `close-after-approval` (close_workorder)
Five conditions, one per sentence of the intent:
1. `site_id == "MAIN"`: close only at MAIN.
2. `context has approval`: there must be an approval on record. Dropping it fails validation, since `approval` is optional.
3. `approval.status == "APPR"`: granted, not pending (`WAPPR` is the real pending status in the data).
4. `approval.wonum == input.wonum`: the approval is for the same work order.
5. `approval.approver != principal`: never self-approved.
Each condition is necessary. Deleting any one admits exactly one universe case the intent forbids (tests: weak_status gives c4, weak_same_wo gives c3, weak_self gives c5; c6 covers condition 1). None is redundant with another.

## Not granted
approve_workorder (explicitly), and every other tool (the intent grants nothing else).

## Known stricter-than-server choice
The server upper-cases `site_id`, so `"main"` would also work there. The reference accepts only `"MAIN"`. That is deliberately stricter, so a deficit on lower-case input is expected and harmless.
