# Clean run 20261112T194818Z-clean-smoke

Model `claude-haiku-5-5` (API reported: claude-haiku-5-5); N=2; generators: naive, Sondera-style (our reimplementation).

| scenario | generator | valid | surplus≠∅ (of valid) | deficit≠∅ (of valid) | symcc: P⊄P_ref | blind spots | rounds | cost (all calls) |
|---|---|---|---|---|---|---|---|---|
| s01_close_after_approval | naive | 2/2 [0.342, 1.0] | 0/2 [0.0, 0.658] | 2/2 [0.342, 1.0] | 2/2 | 2 | — | $0.012 |
| s01_close_after_approval | sondera | 2/2 [0.342, 1.0] | 0/2 [0.0, 0.658] | 1/2 [0.095, 0.905] | 1/2 | 1 | {3: 2} | $0.025 |
| s02_site_scoped_reads | naive | 1/2 [0.095, 0.905] | 0/1 [0.0, 0.793] | 1/1 [0.207, 1.0] | 0/1 | 0 | — | $0.015 |
| s02_site_scoped_reads | sondera | 2/2 [0.342, 1.0] | 0/2 [0.0, 0.658] | 2/2 [0.342, 1.0] | 0/2 | 0 | {1: 1, 2: 1} | $0.020 |
| s03_create_at_main | naive | 2/2 [0.342, 1.0] | 0/2 [0.0, 0.658] | 0/2 [0.0, 0.658] | 0/2 | 0 | — | $0.010 |
| s03_create_at_main | sondera | 2/2 [0.342, 1.0] | 0/2 [0.0, 0.658] | 0/2 [0.0, 0.658] | 0/2 | 0 | {1: 2} | $0.011 |

Intervals: 95% Wilson. Surplus/deficit: enumeration over the scenario universe. symcc: realizable counterexamples (R1/R2 exclusion), per action.
