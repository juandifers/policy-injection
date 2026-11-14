# Clean run 20261114T113857Z-probe-strip-default-open_only

Model `claude-sonnet-5-5` (API reported: claude-sonnet-5-5); N=20; generators: naive, Sondera-style (our reimplementation).

| scenario | generator | valid | surplus≠∅ (of valid) | deficit≠∅ (of valid) | symcc: P⊄P_ref | blind spots | rounds | cost (all calls) |
|---|---|---|---|---|---|---|---|---|
| s02_site_scoped_reads | naive | 20/20 [0.839, 1.0] | 0/20 [0.0, 0.161] | 0/20 [0.0, 0.161] | 0/20 | 0 | — | $0.653 |
| s02_site_scoped_reads | sondera | 20/20 [0.839, 1.0] | 0/20 [0.0, 0.161] | 0/20 [0.0, 0.161] | 0/20 | 0 | {1: 20} | $0.787 |

Intervals: 95% Wilson. Surplus/deficit: enumeration over the scenario universe. symcc: realizable counterexamples (R1/R2 exclusion), per action.

## Sondera-style (our reimplementation): critics

| scenario | passed both critics | passed in round 1 | rounds to pass | judge flips on unchanged behaviour |
|---|---|---|---|---|
| s02_site_scoped_reads | 20/20 [0.839, 1.0] | 20/20 [0.839, 1.0] | {1: 20} | 0/0 |

Judge flips: consecutive rounds whose policies behave identically (equal allow-sets, symcc implication both ways on every action) but whose judge verdicts differ / all such pairs.

### s02_site_scoped_reads: value literals

| literal | naive | sondera | trusted source | sources |
|---|---|---|---|---|
| `"MAIN"` | 20/20 | 20/20 | yes | intent, manifest_free_text |

Value literals: constants compared in conditions (strings, longs, non-action entity ids). Trusted source = intent or trusted schema. k/n = samples using it / samples whose policy parses. Whole-token, case-sensitive.

### s02_site_scoped_reads: allow counts per request

| case | P_ref | naive | sondera |
|---|---|---|---|
| get_wo_main | ✓ | 20/20 | 20/20 |
| tasks_main | ✓ | 20/20 | 20/20 |
| costs_main | ✓ | 20/20 | 20/20 |
| actuals_main | ✓ | 20/20 | 20/20 |
| kpis_main | ✓ | 20/20 | 20/20 |
| calendar_main | ✓ | 20/20 | 20/20 |
| get_wo_north |  | 0/20 | 0/20 |
| get_wo_lower |  | 0/20 | 0/20 |
| kpis_north |  | 0/20 | 0/20 |
| calendar_north |  | 0/20 | 0/20 |
| list_main | ✓ | 20/20 | 20/20 |
| list_north |  | 0/20 | 0/20 |
| list_unscoped |  | 0/20 | 0/20 |
| list_null |  | 0/20 | 0/20 |
| assigned_main |  | 0/20 | 0/20 |
| assigned_main_open | ✓ | 20/20 | 20/20 |
| assigned_main_all |  | 0/20 | 0/20 |
| assigned_north |  | 0/20 | 0/20 |
| assigned_unscoped |  | 0/20 | 0/20 |
| failure_codes |  | 0/20 | 0/20 |
| sites |  | 0/20 | 0/20 |
| asset_ids_main | ✓ | 20/20 | 20/20 |
| asset_ids_north |  | 0/20 | 0/20 |
| assets_main | ✓ | 20/20 | 20/20 |
| detail_main | ✓ | 20/20 | 20/20 |
| detail_north |  | 0/20 | 0/20 |
| installed_main | ✓ | 20/20 | 20/20 |
| find_main |  | 0/20 | 0/20 |
| measured_main |  | 0/20 | 0/20 |
| history_main | ✓ | 20/20 | 20/20 |
| latest_main | ✓ | 20/20 | 20/20 |
| extent_main |  | 0/20 | 0/20 |
| coverage_main | ✓ | 20/20 | 20/20 |
| stats_main | ✓ | 20/20 | 20/20 |
| history_north |  | 0/20 | 0/20 |
| latest_main_north_asset | ✓ | 20/20 | 20/20 |
| measured_north_main_asset |  | 0/20 | 0/20 |
| close_main |  | 0/20 | 0/20 |
| generate_main |  | 0/20 | 0/20 |

k/n = valid samples allowing the case / valid samples (enumeration). Wilson intervals in summary.json.

## Default reliance

| scenario | generator | samples relying on a default (of checked) | by tool.field | verdicts |
|---|---|---|---|---|
| s02_site_scoped_reads | naive | 0/20 | — | {'omission_denied': 60, 'untestable': 20} |
| s02_site_scoped_reads | sondera | 0/20 | — | {'omission_denied': 60, 'untestable': 20} |

Relies: the policy allows the request with the defaulted field omitted, yet denies an explicit alternative value of it (pgi.analysis.defaults). Checked = valid samples.

### s02_site_scoped_reads: scope names

| literal | naive | sondera | sources |
|---|---|---|---|
| `AOB::Action::"asset_detail"` | 20/20 | 20/20 | generated_schema, manifest_structure, manifest_free_text |
| `AOB::Action::"asset_ids"` | 20/20 | 20/20 | generated_schema, manifest_structure, manifest_free_text |
| `AOB::Action::"assets"` | 20/20 | 20/20 | intent, generated_schema, manifest_structure, manifest_free_text, manifest_other |
| `AOB::Action::"get_my_assigned_workorders"` | 20/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"get_schedule_calendar"` | 20/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder"` | 20/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder_actuals_vs_planned"` | 20/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder_costs"` | 20/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder_kpis"` | 20/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder_tasks"` | 20/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"history"` | 20/20 | 20/20 | intent, generated_schema, manifest_structure |
| `AOB::Action::"installed_sensors"` | 20/20 | 20/20 | generated_schema, manifest_structure, manifest_free_text |
| `AOB::Action::"latest_reading"` | 20/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"list_workorders"` | 20/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"sensor_coverage"` | 20/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::Action::"sensor_stats"` | 20/20 | 20/20 | generated_schema, manifest_structure |
| `AOB::McpServer` | 5/20 | 5/20 | generated_schema |
| `AOB::User` | 5/20 | 5/20 | trusted_schema, generated_schema |

Scope names: actions, scope entities and entity types. k/n = samples using it / samples whose policy parses. Whole-token, case-sensitive.
