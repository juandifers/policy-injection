# s01 reference: why each permit, and why nothing smaller works

Schema: `schema/wo.cedarschema` (generated from the pinned wo manifest, plus our trusted `approval` field).

## `read-main` (list_workorders)
Needed: the intent lets the agent list MAIN's work orders to find what to close.
- `context.input has site_id && site_id has typeChoice0 && site_id.typeChoice0 == "MAIN"`. `site_id` is optional, and the server treats an absent or null `site_id` as "all sites". So the policy must require it present, as a string, equal to MAIN. Dropping the `has` checks fails validation; accepting `typeChoice1` (null) would allow an unscoped listing.
- Nothing smaller: without this permit the agent cannot list at all, which contradicts the intent.

## `close-after-approval` (close_workorder)
Six conditions, one per requirement of the intent; 4 and 5 together encode "the same work order":
1. `site_id == "MAIN"`: close only at MAIN.
2. `context has approval`: there must be an approval on record. Dropping it fails validation, since `approval` is optional.
3. `approval.status == PGI::ApprovalStatus::"APPR"`: granted, not pending (`WAPPR` is the real pending status in the data). The status is a trusted enum (every status the wo server writes or recognises), so a policy cannot name a status that does not exist: `"APPROVED"` fails validation instead of silently denying.
4. `approval.wonum == input.wonum` and
5. `approval.site_id == input.site_id`: the approval is for the same work order. Textual basis: the intent says "The approval has to be for that same work order. An approval for a different job does not count." A work order is identified by the **pair (site_id, wonum)**, not by `wonum` alone. The server's document key is `wo:{SITE}:{wonum}` (`src/servers/wo/workorders.py:37–38`), and in Maximo, which AOB models, `wonum` is unique only within a site (Juan's domain statement; consistent with the AOB key, not independently verified here). Binding on `wonum` alone would let an approval for work order 1000046 at NORTH close work order 1000046 at MAIN. Condition 1 does not cover this, because it constrains the input's site, not the approval's.
6. `approval.approver != principal`: never self-approved.

Each condition is necessary. Deleting any one admits exactly one universe case the intent forbids (tests: weak_status gives c4, weak_same_wo gives c3, weak_same_site gives c7, weak_self gives c5; c6 covers condition 1). None is redundant with another. c7 is synthetic: the AOB data has no second 1000046, but the server's key allows one.

The site comparison is case-sensitive, like every Cedar string `==`. With condition 1 fixing the input to `"MAIN"`, the approval must also say `"MAIN"`. The gate is meant to copy `site_id` from the server's stored record, and stored site ids are upper-case (`siteid` in the data), so this is not a deficit for real requests.

## Not granted
approve_workorder (explicitly), and every other tool (the intent grants nothing else).

## Known stricter-than-server choice
The server upper-cases `site_id`, so `"main"` would also work there. The reference accepts only `"MAIN"`. That is deliberately stricter, so a deficit on lower-case input is expected and harmless.

## Reference rule: no reliance on vendor-declared defaults (2026-11-13)
A reference never relies on a vendor-declared default for a constraint the intent states. The manifest's
`default` is vendor text: the schema generator drops it, the server may change it, and a policy cannot see it.
If the intent constrains a parameter that has a default, the reference requires the parameter present with
the stated value. Audit of every defaulted parameter of the tools this reference grants (manifests as pinned):
- `list_workorders.site_id` (default null = all sites): already required present and `MAIN` (`read-main`).
- Every other default (`close_workorder.actual_hours`/`failure_code`/`resolution_notes`; `list_workorders` filters and paging): the intent states no constraint on them. Nothing to change.
