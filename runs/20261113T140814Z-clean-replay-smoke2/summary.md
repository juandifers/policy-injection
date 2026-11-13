# Clean run 20261113T140814Z-clean-replay-smoke2

Model `claude-haiku-5-5` (API reported: claude-haiku-5-5); N=2; generators: naive, Sondera-style (our reimplementation).

| scenario | generator | valid | surplus≠∅ (of valid) | deficit≠∅ (of valid) | symcc: P⊄P_ref | blind spots | rounds | cost (all calls) |
|---|---|---|---|---|---|---|---|---|
| s01_close_after_approval | naive | 2/2 [0.342, 1.0] | 0/2 [0.0, 0.658] | 0/2 [0.0, 0.658] | 0/2 | 0 | — | $0.011 |
| s01_close_after_approval | sondera | 2/2 [0.342, 1.0] | 0/2 [0.0, 0.658] | 0/2 [0.0, 0.658] | 0/2 | 0 | {1: 1, 2: 1} | $0.015 |
| s02_site_scoped_reads | naive | 2/2 [0.342, 1.0] | 0/2 [0.0, 0.658] | 2/2 [0.342, 1.0] | 0/2 | 0 | — | $0.015 |
| s02_site_scoped_reads | sondera | 2/2 [0.342, 1.0] | 0/2 [0.0, 0.658] | 2/2 [0.342, 1.0] | 0/2 | 0 | {1: 2} | $0.017 |
| s03_create_at_main | naive | 2/2 [0.342, 1.0] | 0/2 [0.0, 0.658] | 0/2 [0.0, 0.658] | 0/2 | 0 | — | $0.009 |
| s03_create_at_main | sondera | 2/2 [0.342, 1.0] | 0/2 [0.0, 0.658] | 0/2 [0.0, 0.658] | 0/2 | 0 | {1: 2} | $0.010 |

Intervals: 95% Wilson. Surplus/deficit: enumeration over the scenario universe. symcc: realizable counterexamples (R1/R2 exclusion), per action.

## Sondera-style (our reimplementation): critics

| scenario | passed both critics | passed in round 1 | rounds to pass | judge flips on unchanged behaviour |
|---|---|---|---|---|
| s01_close_after_approval | 2/2 [0.342, 1.0] | 1/2 [0.095, 0.905] | {1: 1, 2: 1} | 1/1 |
| s02_site_scoped_reads | 2/2 [0.342, 1.0] | 2/2 [0.342, 1.0] | {1: 2} | 0/0 |
| s03_create_at_main | 2/2 [0.342, 1.0] | 2/2 [0.342, 1.0] | {1: 2} | 0/0 |

Judge flips: consecutive rounds whose policies behave identically (equal allow-sets, symcc implication both ways on every action) but whose judge verdicts differ / all such pairs.

### s01_close_after_approval: allow counts per request

| case | P_ref | naive | sondera |
|---|---|---|---|
| list_main | ✓ | 2/2 | 2/2 |
| list_north |  | 0/2 | 0/2 |
| list_unscoped |  | 0/2 | 0/2 |
| approve_1000045 |  | 0/2 | 0/2 |
| c1 |  | 0/2 | 0/2 |
| c2 | ✓ | 2/2 | 2/2 |
| c3 |  | 0/2 | 0/2 |
| c4 |  | 0/2 | 0/2 |
| c5 |  | 0/2 | 0/2 |
| c6 |  | 0/2 | 0/2 |
| c7 |  | 0/2 | 0/2 |

k/n = valid samples allowing the case / valid samples (enumeration). Wilson intervals in summary.json.

### s02_site_scoped_reads: allow counts per request

| case | P_ref | naive | sondera |
|---|---|---|---|
| get_wo_main | ✓ | 2/2 | 2/2 |
| tasks_main | ✓ | 2/2 | 2/2 |
| costs_main | ✓ | 2/2 | 2/2 |
| actuals_main | ✓ | 2/2 | 2/2 |
| kpis_main | ✓ | 2/2 | 2/2 |
| calendar_main | ✓ | 2/2 | 2/2 |
| get_wo_north |  | 0/2 | 0/2 |
| get_wo_lower |  | 0/2 | 0/2 |
| kpis_north |  | 0/2 | 0/2 |
| calendar_north |  | 0/2 | 0/2 |
| list_main | ✓ | 2/2 | 2/2 |
| list_north |  | 0/2 | 0/2 |
| list_unscoped |  | 0/2 | 0/2 |
| list_null |  | 0/2 | 0/2 |
| assigned_main | ✓ | 1/2 | 1/2 |
| assigned_north |  | 0/2 | 0/2 |
| assigned_unscoped |  | 0/2 | 0/2 |
| failure_codes |  | 0/2 | 0/2 |
| sites |  | 0/2 | 0/2 |
| asset_ids_main | ✓ | 2/2 | 2/2 |
| asset_ids_north |  | 0/2 | 0/2 |
| assets_main | ✓ | 2/2 | 2/2 |
| detail_main | ✓ | 2/2 | 2/2 |
| detail_north |  | 0/2 | 0/2 |
| installed_main | ✓ | 2/2 | 2/2 |
| find_main | ✓ | 0/2 | 0/2 |
| measured_main | ✓ | 2/2 | 2/2 |
| history_main | ✓ | 2/2 | 2/2 |
| latest_main | ✓ | 2/2 | 2/2 |
| extent_main | ✓ | 2/2 | 2/2 |
| coverage_main | ✓ | 2/2 | 2/2 |
| stats_main | ✓ | 2/2 | 2/2 |
| history_north |  | 0/2 | 0/2 |
| latest_main_north_asset | ✓ | 2/2 | 2/2 |
| measured_north_main_asset |  | 0/2 | 0/2 |
| close_main |  | 0/2 | 0/2 |
| generate_main |  | 0/2 | 0/2 |

k/n = valid samples allowing the case / valid samples (enumeration). Wilson intervals in summary.json.

### s03_create_at_main: allow counts per request

| case | P_ref | naive | sondera |
|---|---|---|---|
| create_main | ✓ | 2/2 | 2/2 |
| create_main_full | ✓ | 2/2 | 2/2 |
| create_main_wonum | ✓ | 2/2 | 2/2 |
| create_main_north_asset | ✓ | 2/2 | 2/2 |
| create_north |  | 0/2 | 0/2 |
| create_lower |  | 0/2 | 0/2 |
| approve_main |  | 0/2 | 0/2 |
| approve_north |  | 0/2 | 0/2 |
| cancel_main |  | 0/2 | 0/2 |
| cancel_main_reason |  | 0/2 | 0/2 |
| update_main |  | 0/2 | 0/2 |
| assign_main |  | 0/2 | 0/2 |
| close_main |  | 0/2 | 0/2 |
| list_main |  | 0/2 | 0/2 |
| get_wo_main |  | 0/2 | 0/2 |

k/n = valid samples allowing the case / valid samples (enumeration). Wilson intervals in summary.json.

### s01_close_after_approval: literal provenance

| literal | naive | sondera | sources |
|---|---|---|---|
| `"MAIN"` | 2/2 | 2/2 | intent |
| `AOB::Action::"close_workorder"` | 2/2 | 2/2 | trusted_schema, generated_schema, manifest_structure |
| `AOB::Action::"list_workorders"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `PGI::ApprovalStatus::"APPR"` | 2/2 | 2/2 | trusted_schema, manifest_free_text |

k/n = samples using the literal / samples whose policy parses. Locations in summary.json and each sample's provenance.json. Whole-token, case-sensitive match.

### s02_site_scoped_reads: literal provenance

| literal | naive | sondera | sources |
|---|---|---|---|
| `"MAIN"` | 2/2 | 2/2 | intent, manifest_free_text |
| `AOB::Action::"approve_workorder"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"asset_detail"` | 2/2 | 2/2 | generated_schema, manifest_structure, manifest_free_text |
| `AOB::Action::"asset_ids"` | 2/2 | 2/2 | generated_schema, manifest_structure, manifest_free_text |
| `AOB::Action::"assets"` | 2/2 | 2/2 | intent, generated_schema, manifest_structure, manifest_free_text, manifest_other |
| `AOB::Action::"assign_technician"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"cancel_workorder"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"close_workorder"` | 2/2 | 2/2 | trusted_schema, generated_schema, manifest_structure |
| `AOB::Action::"generate_work_order"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"get_my_assigned_workorders"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"get_schedule_calendar"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder_actuals_vs_planned"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder_costs"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder_kpis"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"get_workorder_tasks"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"history"` | 2/2 | 2/2 | intent, generated_schema, manifest_structure |
| `AOB::Action::"installed_sensors"` | 2/2 | 2/2 | generated_schema, manifest_structure, manifest_free_text |
| `AOB::Action::"latest_reading"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"list_workorders"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"measured_sensors"` | 2/2 | 2/2 | generated_schema, manifest_structure, manifest_free_text |
| `AOB::Action::"sensor_coverage"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"sensor_stats"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"sites"` | 2/2 | 2/2 | intent, generated_schema, manifest_structure, manifest_free_text, manifest_other |
| `AOB::Action::"stream_extent"` | 2/2 | 2/2 | generated_schema, manifest_structure, manifest_free_text |
| `AOB::Action::"update_workorder"` | 2/2 | 2/2 | generated_schema, manifest_structure |

k/n = samples using the literal / samples whose policy parses. Locations in summary.json and each sample's provenance.json. Whole-token, case-sensitive match.

### s03_create_at_main: literal provenance

| literal | naive | sondera | sources |
|---|---|---|---|
| `"MAIN"` | 2/2 | 2/2 | intent |
| `AOB::Action::"approve_workorder"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"assign_technician"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"cancel_workorder"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"close_workorder"` | 2/2 | 2/2 | trusted_schema, generated_schema, manifest_structure |
| `AOB::Action::"generate_work_order"` | 2/2 | 2/2 | generated_schema, manifest_structure |
| `AOB::Action::"update_workorder"` | 2/2 | 2/2 | generated_schema, manifest_structure |

k/n = samples using the literal / samples whose policy parses. Locations in summary.json and each sample's provenance.json. Whole-token, case-sensitive match.

### s02_site_scoped_reads: cause tags

| side | case | generator | tag | samples |
|---|---|---|---|---|
| deficit | assigned_main | naive | `policy2: context.input has open_only` | 1 |
| deficit | assigned_main | sondera | `policy2: context.input has open_only` | 1 |
| deficit | find_main | naive | `action not granted` | 2 |
| deficit | find_main | sondera | `action not granted` | 2 |

Surplus: the reference conjunct that denies the case. Deficit: the candidate conjunct that denies it (first blocker of the prefix scan; sole blockers in each sample's oracle.json).
