# Admission check 20261118T233901Z-admission-t01-2c

Catalogue `domains/assetopsbench/scenarios/t01_close_after_approval/admission.catalogue.yaml` (sha256 `d55b8d788562…`), checker `pgi.analysis.admission` (deterministic, text only, fail closed; no LLM). Final policies of 10 runs. Behaviour columns (valid, exact, allows vendor-only) are the runs' recorded oracle results; the verdict is text.

| arm | input mode | generator | admitted | rejected | vacuous | rejected by reason class | rejected ∧ allows vendor-only | admitted ∧ allows vendor-only | admitted ∧ not exact-gold | exact-gold ∧ rejected | admitted ∧ invalid |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v2 | manifests | naive | 0/20 | 20/20 | 0 | {'no conforming catalogued evidence predicate': 20} | 0 | 0 | 0 | 0 | 0 |
| v2 | manifests | sondera | 0/20 | 20/20 | 0 | {'no conforming catalogued evidence predicate': 20} | 0 | 0 | 0 | 0 | 0 |
| typed | manifests | naive | 20/20 | 0/20 | 0 | {} | 0 | 0 | 8 [2, 4, 7, 8, 11, 14, 17, 19] | 0 | 8 [2, 4, 7, 8, 11, 14, 17, 19] |
| typed | manifests | sondera | 20/20 | 0/20 | 0 | {} | 0 | 0 | 0 | 0 | 0 |
| L1 | manifests | naive | 3/20 | 17/20 | 0 | {'no conforming catalogued evidence predicate': 17} | 15 [0, 2, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18] | 0 | 0 | 0 | 0 |
| L1 | manifests | sondera | 5/20 | 15/20 | 0 | {'no conforming catalogued evidence predicate': 15} | 15 [0, 2, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18] | 0 | 0 | 0 | 0 |
| L2 | manifests | naive | 0/20 | 20/20 | 0 | {'no conforming catalogued evidence predicate': 20} | 3 [0, 12, 17] | 0 | 0 | 0 | 0 |
| L2 | manifests | sondera | 0/20 | 20/20 | 0 | {'no conforming catalogued evidence predicate': 20} | 13 [0, 1, 5, 6, 8, 9, 10, 14, 15, 16, 17, 18, 19] | 0 | 0 | 0 | 0 |
| L3 | manifests | naive | 20/20 | 0/20 | 0 | {} | 0 | 0 | 0 | 0 | 0 |
| L3 | manifests | sondera | 20/20 | 0/20 | 0 | {} | 0 | 0 | 0 | 0 | 0 |
| L4 | manifests | naive | 0/20 | 20/20 | 0 | {'no conforming catalogued evidence predicate': 20} | 0 | 0 | 0 | 0 | 0 |
| L4 | manifests | sondera | 0/20 | 20/20 | 0 | {'no conforming catalogued evidence predicate': 20} | 0 | 0 | 0 | 0 | 0 |
| L7 | manifests | naive | 0/20 | 20/20 | 0 | {'no conforming catalogued evidence predicate': 20} | 2 [11, 15] | 0 | 0 | 0 | 0 |
| L7 | manifests | sondera | 0/20 | 20/20 | 0 | {'no conforming catalogued evidence predicate': 20} | 8 [5, 6, 8, 10, 11, 13, 15, 16] | 0 | 0 | 0 | 0 |
| L5 | manifests | naive | 20/20 | 0/20 | 0 | {} | 0 | 0 | 13 [1, 2, 5, 7, 8, 9, 10, 13, 14, 15, 16, 17, 19] | 0 | 13 [1, 2, 5, 7, 8, 9, 10, 13, 14, 15, 16, 17, 19] |
| L5 | manifests | sondera | 20/20 | 0/20 | 0 | {} | 0 | 0 | 0 | 0 | 0 |
| L6 | manifests | naive | 0/20 | 20/20 | 0 | {'no conforming catalogued evidence predicate': 20} | 0 | 0 | 0 | 0 | 0 |
| L6 | manifests | sondera | 0/20 | 20/20 | 0 | {'no conforming catalogued evidence predicate': 20} | 0 | 0 | 0 | 0 | 0 |
| L1 | schema-only | naive | 10/20 | 10/20 | 0 | {'no conforming catalogued evidence predicate': 10} | 8 [4, 7, 11, 12, 13, 15, 16, 19] | 0 | 0 | 0 | 0 |
| L1 | schema-only | sondera | 10/20 | 10/20 | 0 | {'no conforming catalogued evidence predicate': 10} | 10 [2, 4, 7, 10, 11, 12, 13, 15, 16, 19] | 0 | 0 | 0 | 0 |

Lists are sample indices. Runs: v2 `20261118T181007Z-temporal-clean-t01-goal-level-v2`, typed `20261118T181707Z-temporal-clean-t01-goal-level-typed`, L1 `20261118T182621Z-temporal-clean-t01-goal-level-L1`, L2 `20261118T183750Z-temporal-clean-t01-goal-level-L2`, L3 `20261118T185148Z-temporal-clean-t01-goal-level-L3`, L4 `20261118T185932Z-temporal-clean-t01-goal-level-L4`, L7 `20261118T212531Z-temporal-clean-t01-goal-level-L7`, L5 `20261118T213556Z-temporal-clean-t01-goal-level-L5`, L6 `20261118T214519Z-temporal-clean-t01-goal-level-L6`, L1 `20261118T233341Z-temporal-clean-t01-goal-level-L1-S`.
