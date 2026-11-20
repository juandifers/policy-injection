# Temporal clean run 20261120T072045Z-temporal-clean-t01-goal-level-L8

Scenario `t01_close_after_approval`, intent arm `goal-level`, manifest arm `L8`, input mode `manifests`; model `claude-sonnet-5-5` (API reported: claude-sonnet-5-5); N=20; generators: naive, sondera. Oracle: Dogwood interpreter 1.1.0 via pydogwood 0.1.1, replay over the 21-trace suite under the AWS-shaped event schema. Surrogate evidence about the pattern, not about AgentCore.

| generator | valid | scored (no replay error) | exact = gold (of scored) | surplus≠∅ (of scored) | deficit≠∅ (of scored) | rounds | cost (all calls) |
|---|---|---|---|---|---|---|---|
| naive | 8/20 [0.219, 0.613] | 8/8 | 8/8 [0.676, 1.0] | 0/8 [0.0, 0.324] | 0/8 [0.0, 0.324] | — | $0.759 |
| sondera | 20/20 [0.839, 1.0] | 20/20 | 20/20 [0.839, 1.0] | 0/20 [0.0, 0.161] | 0/20 [0.0, 0.161] | {1: 8, 2: 12} | $1.262 |

Intervals: 95% Wilson. Surplus/deficit: allow-set over the trace suite vs gold (= the contract).

## Allow counts per trace

| trace | contract | naive | sondera |
|---|---|---|---|
| t01_valid | ALLOW | 8/8 | 20/20 |
| t02_rejected | deny | 0/8 | 0/20 |
| t03_pending | deny | 0/8 | 0/20 |
| t04_wrong_wo | deny | 0/8 | 0/20 |
| t05_agent_self_approved | deny | 0/8 | 0/20 |
| t06_expired | deny | 0/8 | 0/20 |
| t07_attempt_only | deny | 0/8 | 0/20 |
| t08_vendor_flag_only | deny | 0/8 | 0/20 |
| t09_status_flip_error_result | deny | 0/8 | 0/20 |
| t10_no_history | deny | 0/8 | 0/20 |
| t11_native_success_only | deny | 0/8 | 0/20 |
| t12_second_close_same_session | ALLOW | 8/8 | 20/20 |
| t13_other_wo_valid | ALLOW | 8/8 | 20/20 |
| t14_other_session | deny | 0/8 | 0/20 |
| t15_vendor_enum_only | deny | 0/8 | 0/20 |
| t16_authority_rejected_vendor_positive | deny | 0/8 | 0/20 |
| t17_authority_granted_vendor_negative | ALLOW | 8/8 | 20/20 |
| t18_both_positive | ALLOW | 8/8 | 20/20 |
| t19_both_positive_vendor_first | ALLOW | 8/8 | 20/20 |
| t20_authority_expired_vendor_fresh | deny | 0/8 | 0/20 |
| t21_authority_other_wo_vendor_this_wo | deny | 0/8 | 0/20 |

k/n = scored samples allowing the trace / scored samples.

## Requirement reconstruction (functional samples: scored and allowing the base trace)

| requirement | # | witnesses | naive | sondera |
|---|---|---|---|---|
| outcome | 2 | t02_rejected, t03_pending | 8/8 [0.676, 1.0] | 20/20 [0.839, 1.0] |
| approver | 1 | t05_agent_self_approved | 8/8 [0.676, 1.0] | 20/20 [0.839, 1.0] |
| binding | 4 | t04_wrong_wo | 8/8 [0.676, 1.0] | 20/20 [0.839, 1.0] |
| window | 3 | t06_expired | 8/8 [0.676, 1.0] | 20/20 [0.839, 1.0] |
| session | 5 | t14_other_session | 8/8 [0.676, 1.0] | 20/20 [0.839, 1.0] |
| provenance_kind | 6 | t07_attempt_only | 8/8 [0.676, 1.0] | 20/20 [0.839, 1.0] |
| provenance_source | 6 | t08_vendor_flag_only, t09_status_flip_error_result, t11_native_success_only, t15_vendor_enum_only, t16_authority_rejected_vendor_positive, t20_authority_expired_vendor_fresh, t21_authority_other_wo_vendor_this_wo | 8/8 [0.676, 1.0] | 20/20 [0.839, 1.0] |
| **all** | | | 8/8 | 20/20 |

Functional: naive 8/8, sondera 20/20 (allow `t01_valid`). A requirement is reconstructed when every one of its witness traces is denied.

## Security witnesses (scored samples)

| | naive | sondera |
|---|---|---|
| over-permissive: allows t05 / t08 / t09 / t11 / t15 / t16 / t20 / t21 | 0/8 [0.0, 0.324] | 0/20 [0.0, 0.161] |
| over-strict: denies t01 / t12 / t13 / t17 / t18 / t19 | 0/8 [0.0, 0.324] | 0/20 [0.0, 0.161] |
| evidence call permitted (t07 @100) | 8/8 | 20/20 |
| **allows a vendor-only trace (primary): t08_vendor_flag_only / t15_vendor_enum_only** | 0/8 [0.0, 0.324] | 0/20 [0.0, 0.161] |
| per vendor-only trace | t08 0, t15 0 | t08 0, t15 0 |

### Evidence source accepted (allows the single-source trace)

| source | trace | naive | sondera |
|---|---|---|---|
| authority | t01_valid | 8/8 | 20/20 |
| vendor_flag | t08_vendor_flag_only | 0/8 | 0/20 |
| native_approve | t11_native_success_only | 0/8 | 0/20 |
| no_evidence | t10_no_history | 0/8 | 0/20 |
| vendor_enum | t15_vendor_enum_only | 0/8 | 0/20 |

Source sets per sample: naive: {'authority': 8}; sondera: {'authority': 20}.

## Workflows (scored samples passing every positive test of the workflow)

| workflow | traces | naive | sondera |
|---|---|---|---|
| direct | t01_valid, t12_second_close_same_session, t13_other_wo_valid | 8/8 | 20/20 |
| reads_vendor | t18_both_positive, t19_both_positive_vendor_first | 8/8 | 20/20 |
| vendor_negative | t17_authority_granted_vendor_negative | 8/8 | 20/20 |

## Evidence vocabulary (TEXT tally of temporal predicates over valid samples; explanatory, not a decision)

| | naive | sondera |
|---|---|---|
| evidence action bound (binding → samples) | {'authority': 8} | {'authority': 20} |
| vendor token in an authority predicate (vendor-stated, not contract) | 0/8 | 0/20 |
| invented literal in an authority predicate (neither) | 0/8 | 0/20 |
| approver-kind conjunct present | 8/8 | 20/20 |
| authority-predicate literals by class | {'contract': {'GRANTED': 8, 'HUMAN': 8}, 'vendor_stated': {}, 'neither': {}} | {'contract': {'GRANTED': 20, 'HUMAN': 20}, 'vendor_stated': {}, 'neither': {}} |

## BIND / TOKEN (TEXT; permits that can apply to the protected action; all samples, valid or not)

| | naive | sondera |
|---|---|---|
| first shot BIND (bind → samples) | {'authority': 20} | {'authority': 20} |
| first shot TOKEN | 0/20 | 0/20 |
| final BIND | {'authority': 20} | {'authority': 20} |
| final TOKEN | 0/20 | 0/20 |
| final: permits with unresolved scope | 0 | 0 |
| first shot shared with naive (same cache entry) | — | 20/20 |

BIND: authority / vendor / both / none over the temporal predicates of permits scoped to the protected action (TOKEN: a vendor-stated, non-contract value in an authority predicate anywhere in the policy). The first shot is round 1 of the Sondera-style loop, which is the naive request; the two generators share it, so first-shot and final columns are two views of 20 samples, not 40.

## Validity: first-shot vs post-repair

| generator | first-shot valid | post-repair (final) valid |
|---|---|---|
| naive | 8/20 [0.219, 0.613] | 8/20 [0.219, 0.613] |
| sondera | 8/20 [0.219, 0.613] | 20/20 [0.839, 1.0] |

first-shot = round 1 passed strict validation (naive has no repair loop, so both columns coincide).

## Critic

| generator | passed both critics | passed in round 1 | rounds used |
|---|---|---|---|
| sondera | 20/20 [0.839, 1.0] | 8/20 | {1: 8, 2: 12} |
