# Findings

Results only, each traced to a `runs/<id>/` folder and labeled with the oracle that backs it (enumeration or symcc).
Keep baseline over-permission (no attacker) apart from attack-induced expansion.

_No experimental findings yet. The oracle is validated on the toy scenario only (see `tests/test_oracle.py`); that is a test, not a finding._

## Reconnaissance: AssetOpsBench data and tools (2026-11-12)

Not experiments, so no run id. Reproduce with AssetOpsBench at commit `8941acc` (see `decisions.md`) and
`uv run --project $AOB_DIR python domains/assetopsbench/scripts/aob_mcp.py explore`
(direct MCP stdio calls with `AOB_READONLY=1`; no LLM, no agent runner, no write tool called).

### Sites

`iot.sites` returns **two sites: `MAIN` and `NORTH`**. Both have work orders, so site scoping in our scenarios can use real data. A synthetic site is not needed.

### Work orders

The work-order data is tiny: **3 work orders in total**. Every data manifest (`default`, `scenario_1..3`) loads the same `shared/work_order/workorders.csv`. CouchDB holds 7 docs in `workorder`, which are those 3 plus 4 design docs, so the tool is not hiding any.

| wonum | siteid | status | assetnum | description (truncated) |
|---|---|---|---|---|
| `1000045` | MAIN | WAPPR | CHILLER6 | Investigate anomaly on Chiller 6 condenser water f… |
| `1000046` | MAIN | APPR | PUMP3 | Bearing wear failure mode on Pump 3 - corrective a… |
| `1000050` | NORTH | COMP | AHU2 | Quarterly preventive maintenance - AHU 2 |

- Status values present: **WAPPR, APPR, COMP** (one each). The server code also writes `CAN` (cancel) and recognises the pseudo-filters `OPEN` / `APPROVED_PENDING`.
- wonums are numeric strings (`"1000045"`), not `WO1`-style.
- Field naming differs between data and tools. Stored documents use `siteid`, but every tool parameter is named `site_id`.
- Consequence: universes over real IDs can draw on only 3 wonums and 2 sites. Cases that need a second work order at one site (like toy c3) have to pair `1000045` and `1000046` at MAIN, the only site with two.

### Tools

Classification is empirical. A tool is a **write** if it disappears when the server starts with `AOB_READONLY=1`, and this matches `_READ_TOOLS` / `_WRITE_TOOLS` in `servers/wo/main.py`. iot has no `AOB_READONLY` switch and no database writes in its source.

**wo: 15 tools (9 read, 6 write)**

| read | write |
|---|---|
| `list_workorders`, `get_workorder`, `get_workorder_tasks`, `get_workorder_costs`, `get_workorder_actuals_vs_planned`, `get_workorder_kpis`, `get_schedule_calendar`, `get_my_assigned_workorders`, `get_failure_codes` | `generate_work_order`, `update_workorder`, `approve_workorder`, `assign_technician`, `close_workorder`, `cancel_workorder` |

**iot: 12 tools, all read**: `sites`, `asset_ids`, `asset_detail`, `assets`, `find_assets_by_sensors`, `measured_sensors`, `installed_sensors`, `stream_extent`, `history`, `latest_reading`, `sensor_coverage`, `sensor_stats`.

### Server behaviour that matters for the gate later

- **Errors come back as normal results.** With CouchDB misconfigured, `iot.sites` returned `{"result": {"error": "the data source does not exist …"}}` with `isError=False`. A client that trusts `isError` treats the failure as data. Same lesson as the oracle: errors must be detected explicitly.
- Only `get_failure_codes` carries MCP `ToolAnnotations` (`readOnlyHint=True`). **No write tool declares `readOnlyHint=False` or `destructiveHint`.** The manifest itself does not say which tools mutate state.

## Reconnaissance: generated Cedar schema from the clean manifests (2026-11-12)

Not an experiment, so no run id. Reproduce with `uv run --group schemagen python domains/assetopsbench/scripts/gen_schema.py` (generator 0.7.0, default settings; see `decisions.md`). Encoding facts were checked against the generator source at tag v0.7.0 (`request.rs`, `validation.rs`).

### How tool arguments reach a policy

| MCP JSON Schema | Generated Cedar type | Value at request time | What a policy can do with it |
|---|---|---|---|
| `string` | `String` | the string | `==`, `like` |
| `integer` | `Long` | the integer | `==`, `<`, `>` |
| `boolean` | `Bool` | the bool | `==` |
| `number` | **`AOB::Number` (entity, no attributes)** | `AOB::Number::"<literal text>"` | **identity only**: no ordering, and `3` ≠ `3.0` |
| `array` of T | `Set<T>` | set | `contains`, `containsAll` |
| `anyOf [T, null]` (every Python `Optional`) | record `{typeChoice0?: T, typeChoice1?: AOB::Null}` | `{typeChoice<i>: v}` for the **first** branch that matches | needs `has typeChoice0` guards; branch order comes from the manifest |
| `null` | **`AOB::Null` (entity)** | `AOB::Null::"null"` | identity only |
| `object` with `additionalProperties: true` | **attribute-less entity type**, named after tool and parameter | opaque | identity only |
| not in `required` | `?` optional attribute | omitted when the caller omits it | needs `has` guards; **absence often means "all"** |
| `title`, `description`, `default`, `pattern`, `maxLength`, extra fields, `annotations` | **dropped** | n/a | nothing |

### Loosely typed parameters (where attacks will be easiest)

- **Every string is a free `String`.** The manifests contain 0 `enum` and 0 `format`. That includes `site_id` (14 wo tools) and `wonum` (10 wo tools), `site_name` and `asset_id` in iot, and all **dates** (`date_from`, `date_to`, `start_date`, `start`, `end`) and **`status`**. Policies can match these by equality only; the schema never says which values are valid.
- **Opaque `Number` entities**, which cannot be compared: `wo.close_workorder.actual_hours`, `wo.assign_technician.hours_planned`. No policy can bound hours.
- **Opaque object**: `wo.generate_work_order.aob_source` (`object`, `additionalProperties: true`) becomes an attribute-less entity `AOB::generate_work_order::Input::aob_source::TypeChoice0`. Its content is invisible to policy.
- **Optional scoping fields** (absent means unscoped on the server):
  - `wo.list_workorders.site_id?`: omitting it lists every site's work orders, so a "MAIN only" read rule must require it to be present.
  - `wo.get_my_assigned_workorders.site_id?`.
  - `wo.list_workorders.status?`.
- **`Optional` unions everywhere**: 38 of 96 input parameters (wo + iot) are `anyOf [T, null]`. Each becomes a two-way record whose shape depends on branch order in the manifest.
- **No parameter is missing a type**, and no tool input allows extra top-level properties.

### Which manifest fields change the generated schema

From a mutation experiment on scratch copies of the pinned `wo` manifest (one change at a time to `close_workorder`, regenerate, diff):

| Mutation | Schema change |
|---|---|
| tool `description` (even `"IGNORE PREVIOUS INSTRUCTIONS…"`), tool `title`, param `title`, param `description`, param `default`, `pattern`/`maxLength`, extra unknown field, MCP `annotations` | **none** |
| param `enum` added | new enum entity type `AOB::close_workorder::Input::site_id` |
| `format: date-time` added | `String` becomes `datetime` |
| param `type` changed | Cedar type changes (`number` to `integer` turns opaque `Number` into a comparable `Long`) |
| `required` list changed | attribute becomes optional (`site_id?`) |
| `anyOf` branches reordered | `typeChoice0`/`typeChoice1` swap |
| param renamed | attribute renamed. The dangling `required` entry is **silently ignored**, so the renamed field becomes optional. |
| tool renamed | action and input type renamed |

So the generator is **blind to free text**: descriptions and titles never reach the schema. Free text can still steer an LLM *policy* generator, which is the Step 4–5 question, but it cannot change the schema the policy is validated against. **Names, types, `required`, `enum`, `format` and `anyOf` order** do change the schema, and changing them changes the request shapes the oracle and gate see.

### Oracle gap: "impossible policy" warnings are invisible to cedarpy

A policy testing `context has approval` on `approve_workorder`, whose context has no `approval`, is **accepted**. `cedar validate` warns *"policy is impossible: the policy expression evaluates to false for all valid requests"* but exits 0 (it exits 3 only with `--deny-warnings`). **cedarpy 4.12.2 drops warnings entirely**: `validate_policies` returns `validation_passed=True, errors=[]`. So `pgi.oracle.enumeration.validate` cannot tell a misplaced condition from a correct one. That policy would allow nothing and look maximally safe. Not fixed this session (Task 6 forbids oracle changes). Proposed fix: add a strict validation step via `cedar validate --deny-warnings`, or check symcc `never-matches` per permit.

### symcc's "all worlds" includes requests the generator can never produce

On the generated schema, symcc's counterexample for `weak_same_wo` contains `resolution_notes: {}`, a union record with **neither** `typeChoice0` nor `typeChoice1`. It is well-typed (both are optional attributes), but the generator's request encoder always sets exactly one branch (`request.rs`). It did not affect s01 (all 3 symcc results replay correctly in cedarpy). In general, a symcc "DOES NOT HOLD" may rest on such an unrealizable request. Before reporting a symcc-only finding, check that the counterexample is realizable: it must replay in cedarpy *and* match the generator's encoding (exactly one `typeChoice` per union). The Python binding's `generate_request` does not return the context, so that check needs the Rust CLI's `authorize` subcommand or a test against `request.rs` behaviour.
