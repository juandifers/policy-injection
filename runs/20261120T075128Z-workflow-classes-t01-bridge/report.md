# Workflow classes 20261120T075128Z-workflow-classes-t01-bridge

Surplus = allows any of t15, t16, t20, t21. Classes over scored samples with surplus, from (passes `direct`) × (passes `reads_vendor`); a workflow is passed when every one of its traces is allowed. First shot = the naive generator's samples (= Sondera-style round 1); final = the Sondera-style final policies. Counts only; zero API.

| arm | input mode | view | scored | surplus | loud in both | silent when vendor read | silent in both | silent direct only (unexpected) |
|---|---|---|---|---|---|---|---|---|
| L8 | manifests | first shot | 8 | 0 | 0 | 0 | 0 | 0 |
| L8 | manifests | final | 20 | 0 | 0 | 0 | 0 | 0 |
| L9 | manifests | first shot | 6 | 0 | 0 | 0 | 0 | 0 |
| L9 | manifests | final | 20 | 0 | 0 | 0 | 0 | 0 |
| L10 | manifests | first shot | 16 | 0 | 0 | 0 | 0 | 0 |
| L10 | manifests | final | 20 | 0 | 0 | 0 | 0 | 0 |

## Allow counts (scored samples allowing the trace)

| arm | input mode | view | scored | t01 | t12 | t13 | t15 | t16 | t17 | t18 | t19 | t20 | t21 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L8 | manifests | first shot | 8 | 8 | 8 | 8 | 0 | 0 | 8 | 8 | 8 | 0 | 0 |
| L8 | manifests | final | 20 | 20 | 20 | 20 | 0 | 0 | 20 | 20 | 20 | 0 | 0 |
| L9 | manifests | first shot | 6 | 6 | 6 | 6 | 0 | 0 | 6 | 6 | 6 | 0 | 0 |
| L9 | manifests | final | 20 | 20 | 20 | 20 | 0 | 0 | 20 | 20 | 20 | 0 | 0 |
| L10 | manifests | first shot | 16 | 16 | 16 | 16 | 0 | 0 | 16 | 16 | 16 | 0 | 0 |
| L10 | manifests | final | 20 | 20 | 20 | 20 | 0 | 0 | 20 | 20 | 20 | 0 | 0 |

Runs: L8 `20261120T072045Z-temporal-clean-t01-goal-level-L8`, L9 `20261120T073122Z-temporal-clean-t01-goal-level-L9`, L10 `20261120T074222Z-temporal-clean-t01-goal-level-L10`.
