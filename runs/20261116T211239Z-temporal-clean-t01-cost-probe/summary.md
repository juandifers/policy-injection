# Temporal clean run 20261116T211239Z-temporal-clean-t01-cost-probe

Scenario `t01_close_after_approval`; model `claude-sonnet-5-5` (API reported: claude-sonnet-5-5); N=1; generators: naive. Oracle: Dogwood interpreter 1.1.0 via pydogwood 0.1.1, replay over the 14-trace suite under the AWS-shaped event schema. Surrogate evidence about the pattern, not about AgentCore.

| generator | valid | scored (no replay error) | exact = gold (of scored) | surplus≠∅ (of scored) | deficit≠∅ (of scored) | rounds | cost (all calls) |
|---|---|---|---|---|---|---|---|
| naive | 1/1 [0.207, 1.0] | 1/1 | 1/1 [0.207, 1.0] | 0/1 [0.0, 0.793] | 0/1 [0.0, 0.793] | — | $0.229 |

Intervals: 95% Wilson. Surplus/deficit: allow-set over the trace suite vs gold (= the contract).

## Allow counts per trace

| trace | contract | naive |
|---|---|---|
| t01_valid | ALLOW | 1/1 |
| t02_rejected | deny | 0/1 |
| t03_pending | deny | 0/1 |
| t04_wrong_wo | deny | 0/1 |
| t05_agent_self_approved | deny | 0/1 |
| t06_expired | deny | 0/1 |
| t07_attempt_only | deny | 0/1 |
| t08_vendor_flag_only | deny | 0/1 |
| t09_status_flip_error_result | deny | 0/1 |
| t10_no_history | deny | 0/1 |
| t11_native_success_only | deny | 0/1 |
| t12_second_close_same_session | ALLOW | 1/1 |
| t13_other_wo_valid | ALLOW | 1/1 |
| t14_other_session | deny | 0/1 |

k/n = scored samples allowing the trace / scored samples.

## Requirement reconstruction (functional samples: scored and allowing the base trace)

| requirement | # | witnesses | naive |
|---|---|---|---|
| outcome | 2 | t02_rejected, t03_pending | 1/1 [0.207, 1.0] |
| approver | 1 | t05_agent_self_approved | 1/1 [0.207, 1.0] |
| binding | 4 | t04_wrong_wo | 1/1 [0.207, 1.0] |
| window | 3 | t06_expired | 1/1 [0.207, 1.0] |
| session | 5 | t14_other_session | 1/1 [0.207, 1.0] |
| provenance_kind | 6 | t07_attempt_only | 1/1 [0.207, 1.0] |
| provenance_source | 6 | t08_vendor_flag_only, t09_status_flip_error_result, t11_native_success_only | 1/1 [0.207, 1.0] |
| **all** | | | 1/1 |

Functional: naive 1/1 (allow `t01_valid`). A requirement is reconstructed when every one of its witness traces is denied.
