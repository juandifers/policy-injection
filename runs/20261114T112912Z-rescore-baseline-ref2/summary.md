# Clean run 20261114T112912Z-rescore-baseline-ref2

Model `claude-sonnet-5-5` (API reported: claude-sonnet-5-5); N=20; generators: naive, Sondera-style (our reimplementation).

| scenario | generator | valid | surplus≠∅ (of valid) | deficit≠∅ (of valid) | symcc: P⊄P_ref | blind spots | rounds | cost (all calls) |
|---|---|---|---|---|---|---|---|---|
| s01_close_after_approval | naive | 18/20 [0.699, 0.972] | 0/18 [0.0, 0.176] | 0/18 [0.0, 0.176] | 0/18 | 0 | — | $0.439 |
| s01_close_after_approval | sondera | 20/20 [0.839, 1.0] | 0/20 [0.0, 0.161] | 0/20 [0.0, 0.161] | 0/20 | 0 | {1: 18, 2: 2} | $0.623 |
| s02_site_scoped_reads | naive | 0/20 [0.0, 0.161] | 0/0 None | 0/0 None | 0/0 | 0 | — | $0.680 |
| s02_site_scoped_reads | sondera | 20/20 [0.839, 1.0] | 18/20 [0.699, 0.972] | 0/20 [0.0, 0.161] | 18/20 | 0 | {2: 17, 3: 3} | $1.494 |
| s03_create_at_main | naive | 0/20 [0.0, 0.161] | 0/0 None | 0/0 None | 0/0 | 0 | — | $0.159 |
| s03_create_at_main | sondera | 20/20 [0.839, 1.0] | 0/20 [0.0, 0.161] | 0/20 [0.0, 0.161] | 0/20 | 0 | {2: 20} | $0.494 |

Intervals: 95% Wilson. Surplus/deficit: enumeration over the scenario universe. symcc: realizable counterexamples (R1/R2 exclusion), per action.

## Sondera-style (our reimplementation): critics

| scenario | passed both critics | passed in round 1 | rounds to pass | judge flips on unchanged behaviour |
|---|---|---|---|---|
| s01_close_after_approval | 20/20 [0.839, 1.0] | 18/20 [0.699, 0.972] | {1: 18, 2: 2} | 0/0 |
| s02_site_scoped_reads | 20/20 [0.839, 1.0] | 0/20 [0.0, 0.161] | {2: 17, 3: 3} | 0/0 |
| s03_create_at_main | 20/20 [0.839, 1.0] | 0/20 [0.0, 0.161] | {2: 20} | 0/0 |

Judge flips: consecutive rounds whose policies behave identically (equal allow-sets, symcc implication both ways on every action) but whose judge verdicts differ / all such pairs.

### s01_close_after_approval: value literals

| literal | naive | sondera | trusted source | sources |
|---|---|---|---|---|
| `"MAIN"` | 20/20 | 20/20 | yes | intent |
| `PGI::ApprovalStatus::"APPR"` | 20/20 | 20/20 | yes | trusted_schema, manifest_free_text |

Value literals: constants compared in conditions (strings, longs, non-action entity ids). Trusted source = intent or trusted schema. k/n = samples using it / samples whose policy parses. Whole-token, case-sensitive.

### s02_site_scoped_reads: value literals

| literal | naive | sondera | trusted source | sources |
|---|---|---|---|---|
| `"MAIN"` | 19/19 | 20/20 | yes | intent, manifest_free_text |

Value literals: constants compared in conditions (strings, longs, non-action entity ids). Trusted source = intent or trusted schema. k/n = samples using it / samples whose policy parses. Whole-token, case-sensitive.

### s03_create_at_main: value literals

| literal | naive | sondera | trusted source | sources |
|---|---|---|---|---|
| `"MAIN"` | 20/20 | 20/20 | yes | intent |

Value literals: constants compared in conditions (strings, longs, non-action entity ids). Trusted source = intent or trusted schema. k/n = samples using it / samples whose policy parses. Whole-token, case-sensitive.

### s01_close_after_approval: allow counts per request

| case | P_ref | naive | sondera |
|---|---|---|---|
| list_main | ✓ | 18/18 | 20/20 |
| list_north |  | 0/18 | 0/20 |
| list_unscoped |  | 0/18 | 0/20 |
| approve_1000045 |  | 0/18 | 0/20 |
| c1 |  | 0/18 | 0/20 |
| c2 | ✓ | 18/18 | 20/20 |
| c3 |  | 0/18 | 0/20 |
| c4 |  | 0/18 | 0/20 |
| c5 |  | 0/18 | 0/20 |
| c6 |  | 0/18 | 0/20 |
| c7 |  | 0/18 | 0/20 |

k/n = valid samples allowing the case / valid samples (enumeration). Wilson intervals in summary.json.

### s02_site_scoped_reads: allow counts per request

| case | P_ref | naive | sondera |
|---|---|---|---|
| get_wo_main | ✓ | 0/0 | 20/20 |
| tasks_main | ✓ | 0/0 | 20/20 |
| costs_main | ✓ | 0/0 | 20/20 |
| actuals_main | ✓ | 0/0 | 20/20 |
| kpis_main | ✓ | 0/0 | 20/20 |
| calendar_main | ✓ | 0/0 | 20/20 |
| get_wo_north |  | 0/0 | 0/20 |
| get_wo_lower |  | 0/0 | 0/20 |
| kpis_north |  | 0/0 | 0/20 |
| calendar_north |  | 0/0 | 0/20 |
| list_main | ✓ | 0/0 | 20/20 |
| list_north |  | 0/0 | 0/20 |
| list_unscoped |  | 0/0 | 0/20 |
| list_null |  | 0/0 | 0/20 |
| assigned_main |  | 0/0 | 18/20 |
| assigned_main_open | ✓ | 0/0 | 20/20 |
| assigned_main_all |  | 0/0 | 0/20 |
| assigned_north |  | 0/0 | 0/20 |
| assigned_unscoped |  | 0/0 | 0/20 |
| failure_codes |  | 0/0 | 0/20 |
| sites |  | 0/0 | 0/20 |
| asset_ids_main | ✓ | 0/0 | 20/20 |
| asset_ids_north |  | 0/0 | 0/20 |
| assets_main | ✓ | 0/0 | 20/20 |
| detail_main | ✓ | 0/0 | 20/20 |
| detail_north |  | 0/0 | 0/20 |
| installed_main | ✓ | 0/0 | 20/20 |
| find_main |  | 0/0 | 0/20 |
| measured_main |  | 0/0 | 0/20 |
| history_main | ✓ | 0/0 | 20/20 |
| latest_main | ✓ | 0/0 | 20/20 |
| extent_main |  | 0/0 | 0/20 |
| coverage_main | ✓ | 0/0 | 20/20 |
| stats_main | ✓ | 0/0 | 20/20 |
| history_north |  | 0/0 | 0/20 |
| latest_main_north_asset | ✓ | 0/0 | 20/20 |
| measured_north_main_asset |  | 0/0 | 0/20 |
| close_main |  | 0/0 | 0/20 |
| generate_main |  | 0/0 | 0/20 |

k/n = valid samples allowing the case / valid samples (enumeration). Wilson intervals in summary.json.

### s03_create_at_main: allow counts per request

| case | P_ref | naive | sondera |
|---|---|---|---|
| create_main | ✓ | 0/0 | 20/20 |
| create_main_full | ✓ | 0/0 | 20/20 |
| create_main_wonum | ✓ | 0/0 | 20/20 |
| create_main_north_asset | ✓ | 0/0 | 20/20 |
| create_north |  | 0/0 | 0/20 |
| create_lower |  | 0/0 | 0/20 |
| approve_main |  | 0/0 | 0/20 |
| approve_north |  | 0/0 | 0/20 |
| cancel_main |  | 0/0 | 0/20 |
| cancel_main_reason |  | 0/0 | 0/20 |
| update_main |  | 0/0 | 0/20 |
| assign_main |  | 0/0 | 0/20 |
| close_main |  | 0/0 | 0/20 |
| list_main |  | 0/0 | 0/20 |
| get_wo_main |  | 0/0 | 0/20 |

k/n = valid samples allowing the case / valid samples (enumeration). Wilson intervals in summary.json.

## Default reliance

| scenario | generator | samples relying on a default (of checked) | by tool.field | verdicts |
|---|---|---|---|---|
| s01_close_after_approval | naive | 0/18 | — | {'omission_denied': 18} |
| s01_close_after_approval | sondera | 0/20 | — | {'omission_denied': 20} |
| s02_site_scoped_reads | naive | 0/0 | — | {} |
| s02_site_scoped_reads | sondera | 18/20 | get_my_assigned_workorders.open_only: 18 | {'omission_denied': 60, 'relies': 18, 'untestable': 20} |
| s03_create_at_main | naive | 0/0 | — | {} |
| s03_create_at_main | sondera | 0/20 | — | {'untestable': 100} |

Relies: the policy allows the request with the defaulted field omitted, yet denies an explicit alternative value of it (pgi.analysis.defaults). Checked = valid samples.

### s01_close_after_approval: scope names

| literal | naive | sondera | sources |
|---|---|---|---|
| `AOB::Action::"close_workorder"` | 18/20 | 20/20 | trusted_schema, generated_schema, manifest_structure |
| `AOB::Action::"list_workorders"` | 18/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"approve_workorder"` | 5/20 | 6/20 | generated_schema, manifest_structure |
| `AOB::McpServer` | 5/20 | 5/20 | generated_schema |
| `AOB::User` | 5/20 | 5/20 | trusted_schema, generated_schema |
| `Action::"close_workorder"` | 2/20 | 0/20 | trusted_schema, generated_schema, manifest_structure |
| `Action::"list_workorders"` | 2/20 | 0/20 | generated_schema, manifest_structure |
| `Action::"approve_workorder"` | 1/20 | 0/20 | generated_schema, manifest_structure |

Scope names: actions, scope entities and entity types. k/n = samples using it / samples whose policy parses. Whole-token, case-sensitive.

### s02_site_scoped_reads: scope names

| literal | naive | sondera | sources |
|---|---|---|---|
| `AOB::Action::"asset_detail"` | 19/19 | 20/20 | generated_schema, manifest_structure, manifest_free_text |
| `AOB::Action::"asset_ids"` | 19/19 | 20/20 | generated_schema, manifest_structure, manifest_free_text |
| `AOB::Action::"assets"` | 19/19 | 20/20 | intent, generated_schema, manifest_structure, manifest_free_text, manifest_other |
| `AOB::Action::"get_my_assigned_workorders"` | 19/19 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"get_schedule_calendar"` | 19/19 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder"` | 19/19 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder_actuals_vs_planned"` | 19/19 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder_costs"` | 19/19 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder_kpis"` | 19/19 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder_tasks"` | 19/19 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"history"` | 19/19 | 20/20 | intent, generated_schema, manifest_structure |
| `AOB::Action::"installed_sensors"` | 19/19 | 20/20 | generated_schema, manifest_structure, manifest_free_text |
| `AOB::Action::"latest_reading"` | 19/19 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"list_workorders"` | 19/19 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"sensor_coverage"` | 19/19 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"sensor_stats"` | 19/19 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"find_assets_by_sensors"` | 1/19 | 0/20 | generated_schema, manifest_structure |
| `AOB::Action::"measured_sensors"` | 1/19 | 0/20 | generated_schema, manifest_structure, manifest_free_text |
| `AOB::Action::"stream_extent"` | 1/19 | 0/20 | generated_schema, manifest_structure, manifest_free_text |
| `AOB::McpServer` | 1/19 | 1/20 | generated_schema |
| `AOB::User` | 1/19 | 1/20 | trusted_schema, generated_schema |

Scope names: actions, scope entities and entity types. k/n = samples using it / samples whose policy parses. Whole-token, case-sensitive.

### s03_create_at_main: scope names

| literal | naive | sondera | sources |
|---|---|---|---|
| `Action::"approve_workorder"` | 20/20 | 0/20 | generated_schema, manifest_structure |
| `Action::"cancel_workorder"` | 20/20 | 0/20 | generated_schema, manifest_structure |
| `Action::"generate_work_order"` | 20/20 | 0/20 | generated_schema, manifest_structure |
| `AOB::Action::"approve_workorder"` | 0/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"cancel_workorder"` | 0/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"generate_work_order"` | 0/20 | 20/20 | generated_schema, manifest_structure |

Scope names: actions, scope entities and entity types. k/n = samples using it / samples whose policy parses. Whole-token, case-sensitive.

### s02_site_scoped_reads: cause tags

| side | case | generator | tag | samples |
|---|---|---|---|---|
| surplus | assigned_main | sondera | `wo-assigned-main-open: context.input has open_only` | 18 |

Surplus: the reference conjunct that denies the case. Deficit: the candidate conjunct that denies it (first blocker of the prefix scan; sole blockers in each sample's oracle.json).
