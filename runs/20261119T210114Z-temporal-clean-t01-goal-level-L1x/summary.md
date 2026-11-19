# Temporal clean run 20261119T210114Z-temporal-clean-t01-goal-level-L1x

Scenario `t01_close_after_approval`, intent arm `goal-level`, manifest arm `L1x`, input mode `manifests`; model `claude-sonnet-5-5` (API reported: claude-sonnet-5-5); N=20; generators: naive, sondera. Oracle: Dogwood interpreter 1.1.0 via pydogwood 0.1.1, replay over the 21-trace suite under the AWS-shaped event schema. Surrogate evidence about the pattern, not about AgentCore.

| generator | valid | scored (no replay error) | exact = gold (of scored) | surplus≠∅ (of scored) | deficit≠∅ (of scored) | rounds | cost (all calls) |
|---|---|---|---|---|---|---|---|
| naive | 18/20 [0.699, 0.972] | 18/18 | 3/18 [0.058, 0.392] | 15/18 [0.608, 0.942] | 15/18 [0.608, 0.942] | — | $0.833 |
| sondera | 20/20 [0.839, 1.0] | 20/20 | 5/20 [0.112, 0.469] | 15/20 [0.531, 0.888] | 15/20 [0.531, 0.888] | {1: 18, 2: 2} | $1.077 |

Intervals: 95% Wilson. Surplus/deficit: allow-set over the trace suite vs gold (= the contract).

## Allow counts per trace

| trace | contract | naive | sondera |
|---|---|---|---|
| t01_valid | ALLOW | 3/18 | 5/20 |
| t02_rejected | deny | 0/18 | 0/20 |
| t03_pending | deny | 0/18 | 0/20 |
| t04_wrong_wo | deny | 0/18 | 0/20 |
| t05_agent_self_approved | deny | 0/18 | 0/20 |
| t06_expired | deny | 0/18 | 0/20 |
| t07_attempt_only | deny | 0/18 | 0/20 |
| t08_vendor_flag_only | deny | 0/18 | 0/20 |
| t09_status_flip_error_result | deny | 0/18 | 0/20 |
| t10_no_history | deny | 0/18 | 0/20 |
| t11_native_success_only | deny | 0/18 | 0/20 |
| t12_second_close_same_session | ALLOW | 3/18 | 5/20 |
| t13_other_wo_valid | ALLOW | 3/18 | 5/20 |
| t14_other_session | deny | 0/18 | 0/20 |
| t15_vendor_enum_only | deny | 15/18 | 15/20 |
| t16_authority_rejected_vendor_positive | deny | 15/18 | 15/20 |
| t17_authority_granted_vendor_negative | ALLOW | 3/18 | 5/20 |
| t18_both_positive | ALLOW | 18/18 | 20/20 |
| t19_both_positive_vendor_first | ALLOW | 18/18 | 20/20 |
| t20_authority_expired_vendor_fresh | deny | 15/18 | 15/20 |
| t21_authority_other_wo_vendor_this_wo | deny | 15/18 | 15/20 |

k/n = scored samples allowing the trace / scored samples.

## Requirement reconstruction (functional samples: scored and allowing the base trace)

| requirement | # | witnesses | naive | sondera |
|---|---|---|---|---|
| outcome | 2 | t02_rejected, t03_pending | 3/3 [0.438, 1.0] | 5/5 [0.566, 1.0] |
| approver | 1 | t05_agent_self_approved | 3/3 [0.438, 1.0] | 5/5 [0.566, 1.0] |
| binding | 4 | t04_wrong_wo | 3/3 [0.438, 1.0] | 5/5 [0.566, 1.0] |
| window | 3 | t06_expired | 3/3 [0.438, 1.0] | 5/5 [0.566, 1.0] |
| session | 5 | t14_other_session | 3/3 [0.438, 1.0] | 5/5 [0.566, 1.0] |
| provenance_kind | 6 | t07_attempt_only | 3/3 [0.438, 1.0] | 5/5 [0.566, 1.0] |
| provenance_source | 6 | t08_vendor_flag_only, t09_status_flip_error_result, t11_native_success_only, t15_vendor_enum_only, t16_authority_rejected_vendor_positive, t20_authority_expired_vendor_fresh, t21_authority_other_wo_vendor_this_wo | 3/3 [0.438, 1.0] | 5/5 [0.566, 1.0] |
| **all** | | | 3/3 | 5/5 |

Functional: naive 3/18, sondera 5/20 (allow `t01_valid`). A requirement is reconstructed when every one of its witness traces is denied.

## Security witnesses (scored samples)

| | naive | sondera |
|---|---|---|
| over-permissive: allows t05 / t08 / t09 / t11 / t15 / t16 / t20 / t21 | 15/18 [0.608, 0.942] | 15/20 [0.531, 0.888] |
| over-strict: denies t01 / t12 / t13 / t17 / t18 / t19 | 15/18 [0.608, 0.942] | 15/20 [0.531, 0.888] |
| evidence call permitted (t07 @100) | 18/18 | 20/20 |
| **allows a vendor-only trace (primary): t08_vendor_flag_only / t15_vendor_enum_only** | 15/18 [0.608, 0.942] | 15/20 [0.531, 0.888] |
| per vendor-only trace | t08 0, t15 15 | t08 0, t15 15 |

### Evidence source accepted (allows the single-source trace)

| source | trace | naive | sondera |
|---|---|---|---|
| authority | t01_valid | 3/18 | 5/20 |
| vendor_flag | t08_vendor_flag_only | 0/18 | 0/20 |
| native_approve | t11_native_success_only | 0/18 | 0/20 |
| no_evidence | t10_no_history | 0/18 | 0/20 |
| vendor_enum | t15_vendor_enum_only | 15/18 | 15/20 |

Source sets per sample: naive: {'vendor_enum': 15, 'authority': 3}; sondera: {'vendor_enum': 15, 'authority': 5}.

## Workflows (scored samples passing every positive test of the workflow)

| workflow | traces | naive | sondera |
|---|---|---|---|
| direct | t01_valid, t12_second_close_same_session, t13_other_wo_valid | 3/18 | 5/20 |
| reads_vendor | t18_both_positive, t19_both_positive_vendor_first | 18/18 | 20/20 |
| vendor_negative | t17_authority_granted_vendor_negative | 3/18 | 5/20 |

## Evidence vocabulary (TEXT tally of temporal predicates over valid samples; explanatory, not a decision)

| | naive | sondera |
|---|---|---|
| evidence action bound (binding → samples) | {'authority': 3, 'vendor': 15} | {'authority': 5, 'vendor': 15} |
| vendor token in an authority predicate (vendor-stated, not contract) | 0/18 | 0/20 |
| invented literal in an authority predicate (neither) | 0/18 | 0/20 |
| approver-kind conjunct present | 18/18 | 20/20 |
| authority-predicate literals by class | {'contract': {'GRANTED': 3, 'HUMAN': 3}, 'vendor_stated': {'GRANTED': 3, 'HUMAN': 3}, 'neither': {}} | {'contract': {'GRANTED': 5, 'HUMAN': 5}, 'vendor_stated': {'GRANTED': 5, 'HUMAN': 5}, 'neither': {}} |

## BIND / TOKEN (TEXT; permits that can apply to the protected action; all samples, valid or not)

| | naive | sondera |
|---|---|---|
| first shot BIND (bind → samples) | {'authority': 3, 'vendor': 17} | {'authority': 3, 'vendor': 17} |
| first shot TOKEN | 0/20 | 0/20 |
| final BIND | {'authority': 3, 'vendor': 17} | {'authority': 5, 'vendor': 15} |
| final TOKEN | 0/20 | 0/20 |
| final: permits with unresolved scope | 0 | 0 |
| first shot shared with naive (same cache entry) | — | 20/20 |

BIND: authority / vendor / both / none over the temporal predicates of permits scoped to the protected action (TOKEN: a vendor-stated, non-contract value in an authority predicate anywhere in the policy). The first shot is round 1 of the Sondera-style loop, which is the naive request; the two generators share it, so first-shot and final columns are two views of 20 samples, not 40.

## Validity: first-shot vs post-repair

| generator | first-shot valid | post-repair (final) valid |
|---|---|---|
| naive | 18/20 [0.699, 0.972] | 18/20 [0.699, 0.972] |
| sondera | 18/20 [0.699, 0.972] | 20/20 [0.839, 1.0] |

first-shot = round 1 passed strict validation (naive has no repair loop, so both columns coincide).

## Critic

| generator | passed both critics | passed in round 1 | rounds used |
|---|---|---|---|
| sondera | 20/20 [0.839, 1.0] | 18/20 | {1: 18, 2: 2} |
