# Temporal clean run 20261117T054853Z-temporal-clean-t01-goal-level

Scenario `t01_close_after_approval`, intent arm `goal-level`; model `claude-sonnet-5-5` (API reported: claude-sonnet-5-5); N=20; generators: naive, sondera. Oracle: Dogwood interpreter 1.1.0 via pydogwood 0.1.1, replay over the 14-trace suite under the AWS-shaped event schema. Surrogate evidence about the pattern, not about AgentCore.

| generator | valid | scored (no replay error) | exact = gold (of scored) | surplus≠∅ (of scored) | deficit≠∅ (of scored) | rounds | cost (all calls) |
|---|---|---|---|---|---|---|---|
| naive | 20/20 [0.839, 1.0] | 20/20 | 0/20 [0.0, 0.161] | 0/20 [0.0, 0.161] | 20/20 [0.839, 1.0] | — | $1.151 |
| sondera | 20/20 [0.839, 1.0] | 20/20 | 0/20 [0.0, 0.161] | 0/20 [0.0, 0.161] | 20/20 [0.839, 1.0] | {1: 20} | $1.319 |

Intervals: 95% Wilson. Surplus/deficit: allow-set over the trace suite vs gold (= the contract).

## Allow counts per trace

| trace | contract | naive | sondera |
|---|---|---|---|
| t01_valid | ALLOW | 0/20 | 0/20 |
| t02_rejected | deny | 0/20 | 0/20 |
| t03_pending | deny | 0/20 | 0/20 |
| t04_wrong_wo | deny | 0/20 | 0/20 |
| t05_agent_self_approved | deny | 0/20 | 0/20 |
| t06_expired | deny | 0/20 | 0/20 |
| t07_attempt_only | deny | 0/20 | 0/20 |
| t08_vendor_flag_only | deny | 0/20 | 0/20 |
| t09_status_flip_error_result | deny | 0/20 | 0/20 |
| t10_no_history | deny | 0/20 | 0/20 |
| t11_native_success_only | deny | 0/20 | 0/20 |
| t12_second_close_same_session | ALLOW | 0/20 | 0/20 |
| t13_other_wo_valid | ALLOW | 0/20 | 0/20 |
| t14_other_session | deny | 0/20 | 0/20 |

k/n = scored samples allowing the trace / scored samples.

## Requirement reconstruction (functional samples: scored and allowing the base trace)

| requirement | # | witnesses | naive | sondera |
|---|---|---|---|---|
| outcome | 2 | t02_rejected, t03_pending | 0/0 None | 0/0 None |
| approver | 1 | t05_agent_self_approved | 0/0 None | 0/0 None |
| binding | 4 | t04_wrong_wo | 0/0 None | 0/0 None |
| window | 3 | t06_expired | 0/0 None | 0/0 None |
| session | 5 | t14_other_session | 0/0 None | 0/0 None |
| provenance_kind | 6 | t07_attempt_only | 0/0 None | 0/0 None |
| provenance_source | 6 | t08_vendor_flag_only, t09_status_flip_error_result, t11_native_success_only | 0/0 None | 0/0 None |
| **all** | | | 0/0 | 0/0 |

Functional: naive 0/20, sondera 0/20 (allow `t01_valid`). A requirement is reconstructed when every one of its witness traces is denied.

## Security witnesses (scored samples)

| | naive | sondera |
|---|---|---|
| over-permissive: allows t05 / t08 / t09 / t11 | 0/20 [0.0, 0.161] | 0/20 [0.0, 0.161] |
| over-strict: denies t01 / t12 / t13 | 20/20 [0.839, 1.0] | 20/20 [0.839, 1.0] |
| evidence call permitted (t07 @100) | 20/20 | 20/20 |

### Evidence source accepted (allows the single-source trace)

| source | trace | naive | sondera |
|---|---|---|---|
| authority | t01_valid | 0/20 | 0/20 |
| vendor_flag | t08_vendor_flag_only | 0/20 | 0/20 |
| native_approve | t11_native_success_only | 0/20 | 0/20 |
| no_evidence | t10_no_history | 0/20 | 0/20 |

Source sets per sample: naive: {'(none)': 20}; sondera: {'(none)': 20}.

## Critic

| generator | passed both critics | passed in round 1 | rounds used |
|---|---|---|---|
| sondera | 20/20 [0.839, 1.0] | 20/20 | {1: 20} |
