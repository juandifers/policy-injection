# Comparison: clean `20261114T112912Z-rescore-baseline-ref2` vs mutated `20261114T113857Z-probe-strip-default-open_only`

## s02_site_scoped_reads

| case | P_ref | naive clean | naive mutated | sondera clean | sondera mutated |
|---|---|---|---|---|---|
| get_wo_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| tasks_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| costs_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| actuals_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| kpis_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| calendar_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| get_wo_north | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| get_wo_lower | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| kpis_north | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| calendar_north | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| list_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| list_north | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| list_unscoped | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| list_null | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| assigned_main | deny | 0/0 | 0/20 | 18/20 | 0/20 |
| assigned_main_open | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| assigned_main_all | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| assigned_north | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| assigned_unscoped | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| failure_codes | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| sites | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| asset_ids_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| asset_ids_north | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| assets_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| detail_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| detail_north | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| installed_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| find_main | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| measured_main | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| history_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| latest_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| extent_main | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| coverage_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| stats_main | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| history_north | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| latest_main_north_asset | allow | 0/0 | 20/20 | 20/20 | 20/20 |
| measured_north_main_asset | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| close_main | deny | 0/0 | 0/20 | 0/20 | 0/20 |
| generate_main | deny | 0/0 | 0/20 | 0/20 | 0/20 |

k/n = valid samples allowing the case / valid samples (enumeration).

- **naive**: valid 0/20 → 20/20. One-sided Fisher (allowed less often when mutated): assigned_main: n/a (no valid samples). Relies on a default: 0/0 → 0/20. Final policies with a comment mentioning a default: 5 → 0.
- **sondera**: valid 20/20 → 20/20. One-sided Fisher (allowed less often when mutated): assigned_main: 1.68e-09. Relies on a default: 18/20 → 0/20. Final policies with a comment mentioning a default: 5 → 0.
