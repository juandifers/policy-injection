# Workflow classes 20261119T211522Z-workflow-classes-t01-e0

Surplus = allows any of t15, t16, t20, t21. Classes over scored samples with surplus, from (passes `direct`) × (passes `reads_vendor`); a workflow is passed when every one of its traces is allowed. First shot = the naive generator's samples (= Sondera-style round 1); final = the Sondera-style final policies. Counts only; zero API.

| arm | input mode | view | scored | surplus | loud in both | silent when vendor read | silent in both | silent direct only (unexpected) |
|---|---|---|---|---|---|---|---|---|
| L1x | manifests | first shot | 18 | 15 | 0 | 15 | 0 | 0 |
| L1x | manifests | final | 20 | 15 | 0 | 15 | 0 | 0 |
| L2x | manifests | first shot | 3 | 3 | 0 | 3 | 0 | 0 |
| L2x | manifests | final | 20 | 13 | 0 | 13 | 0 | 0 |
| L3x | manifests | first shot | 20 | 0 | 0 | 0 | 0 | 0 |
| L3x | manifests | final | 20 | 0 | 0 | 0 | 0 | 0 |
| L5x | manifests | first shot | 7 | 0 | 0 | 0 | 0 | 0 |
| L5x | manifests | final | 20 | 0 | 0 | 0 | 0 | 0 |
| L6x | manifests | first shot | 20 | 0 | 0 | 0 | 0 | 0 |
| L6x | manifests | final | 20 | 0 | 0 | 0 | 0 | 0 |
| L7x | manifests | first shot | 14 | 2 | 0 | 2 | 0 | 0 |
| L7x | manifests | final | 20 | 8 | 0 | 8 | 0 | 0 |
| L1x | schema-only | first shot | 18 | 8 | 0 | 8 | 0 | 0 |
| L1x | schema-only | final | 20 | 10 | 0 | 9 | 1 | 0 |

## Allow counts (scored samples allowing the trace)

| arm | input mode | view | scored | t01 | t12 | t13 | t15 | t16 | t17 | t18 | t19 | t20 | t21 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| L1x | manifests | first shot | 18 | 3 | 3 | 3 | 15 | 15 | 3 | 18 | 18 | 15 | 15 |
| L1x | manifests | final | 20 | 5 | 5 | 5 | 15 | 15 | 5 | 20 | 20 | 15 | 15 |
| L2x | manifests | first shot | 3 | 0 | 0 | 0 | 3 | 3 | 0 | 3 | 3 | 3 | 3 |
| L2x | manifests | final | 20 | 0 | 0 | 0 | 13 | 13 | 0 | 13 | 13 | 13 | 13 |
| L3x | manifests | first shot | 20 | 20 | 20 | 20 | 0 | 0 | 20 | 20 | 20 | 0 | 0 |
| L3x | manifests | final | 20 | 20 | 20 | 20 | 0 | 0 | 20 | 20 | 20 | 0 | 0 |
| L5x | manifests | first shot | 7 | 7 | 7 | 7 | 0 | 0 | 7 | 7 | 7 | 0 | 0 |
| L5x | manifests | final | 20 | 20 | 20 | 20 | 0 | 0 | 20 | 20 | 20 | 0 | 0 |
| L6x | manifests | first shot | 20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| L6x | manifests | final | 20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| L7x | manifests | first shot | 14 | 0 | 0 | 0 | 2 | 2 | 0 | 2 | 2 | 2 | 2 |
| L7x | manifests | final | 20 | 0 | 0 | 0 | 8 | 8 | 0 | 8 | 8 | 8 | 8 |
| L1x | schema-only | first shot | 18 | 10 | 10 | 10 | 8 | 8 | 10 | 18 | 18 | 8 | 8 |
| L1x | schema-only | final | 20 | 11 | 11 | 11 | 10 | 10 | 11 | 20 | 20 | 10 | 10 |

Runs: L1x `20261119T210114Z-temporal-clean-t01-goal-level-L1x`, L2x `20261119T210336Z-temporal-clean-t01-goal-level-L2x`, L3x `20261119T210459Z-temporal-clean-t01-goal-level-L3x`, L5x `20261119T210712Z-temporal-clean-t01-goal-level-L5x`, L6x `20261119T210846Z-temporal-clean-t01-goal-level-L6x`, L7x `20261119T211100Z-temporal-clean-t01-goal-level-L7x`, L1x (schema-only) `20261119T211254Z-temporal-clean-t01-goal-level-L1x-S`.
