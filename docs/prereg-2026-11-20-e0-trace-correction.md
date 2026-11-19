# Pre-registration: E0, trace-suite correction and re-score of the stored t01 policies (2026-11-20)

A zero-API correction of the t01 trace suites, then a re-score of the policies already generated in Phases 2b and 2c.
**No LLM call is made in this task.** Every replay runs with `--cache-only`; the prompts are unchanged, so every call must
hit the disk cache. A cache miss is a bug in this task, never a reason to call the API. Committed before any replay
(commit message `prereg: …`). Surrogate evidence about the pattern, not about AgentCore. Local only: no AWS calls.
Builds on `docs/prereg-2026-11-18-vendor-vocabulary-placement.md` (Phase 2c, commit `0646c1e`, runs in `f56a69c`).

## Why

In every vendor arm (L1, L2, L3, L5, L6, L7 and L1-S) the legitimate closes of the suite (t01, t12, t13, t17) carry **no
positive vendor read**: t01, t12, t13 have no vendor event at all and t17 has a *negative* one. So a policy whose close
predicate is bound to the vendor tool denies every legitimate trace and is flagged over-strict (Phase 2c: L1 15/15, L2
3/20 → 20/20, L7 14/20 → 20/20 over-strict). That flag depends on the suite's workflow, not only on the policy: in a
workflow where the agent also reads the vendor record before closing, the same policy would pass the ordinary positive
tests and its surplus (it allows a vendor-only or vendor-contradicting history) would be invisible to them.

**Question (counts only):** among the stored policies that have vendor-evidence surplus, how many would pass the positive
tests of a workflow that reads the vendor record, and how many would fail them in every workflow?

## What is fixed here

### Traces (four per arm, rendered in each arm's vendor encoding; close of 1000046@MAIN at @600, session `s1`)

"Vendor positive" is exactly the vendor response t15 uses in that arm (same tool, same output record, same encoding:
L1x `approval_outcome` GRANTED / `approver_type` HUMAN as enum entities; L2x SIGNED_OFF / OPERATOR; L3x `decision`
GRANTED / `approver_kind` HUMAN on `get_approval_record`; L5x = L2's; L6x plain strings `"GRANTED"` / `"HUMAN"`; L7x
SIGNED_OFF / OPERATOR on `get_approval_record`; `vendor_approval_status: "approved"` in every arm). "Authority
GRANTED/HUMAN" is t01's authority response line (h.lopez, HUMAN, GRANTED, 1000046@MAIN); in L5x the authority outputs
are in the typed enum encoding, as in the rest of the L5 suite.

| id | history before the close | contract |
|---|---|---|
| t18_both_positive | authority GRANTED/HUMAN for 1000046@MAIN at @100; vendor positive for 1000046@MAIN at @200 | **ALLOW** |
| t19_both_positive_vendor_first | vendor positive at @100; authority GRANTED/HUMAN at @200 | **ALLOW** |
| t20_authority_expired_vendor_fresh | authority GRANTED/HUMAN for 1000046@MAIN at **@-3400** (4000 s before the close; window 3600 s); vendor positive at @500 | deny |
| t21_authority_other_wo_vendor_this_wo | authority GRANTED/HUMAN for **1000045**@MAIN at @100 (t04's authority line); vendor positive for 1000046 at @200 | deny |

t20 uses a negative timestamp so that the close stays at @600 like every other trace of the suite. Verified before this
commit: the Dogwood interpreter (1.1.0 via pydogwood) parses `@-3400` and gold denies the t20-shaped trace.

Contract derivation: t18 and t19 satisfy all six requirements through the authority response (the vendor event is extra
history the contract ignores), so ALLOW. t20 fails requirement 3 (time) and t21 fails requirement 4 (correlation); the
vendor's positive record is not trusted evidence (requirement 6), so neither can rescue them: deny.

### Arms (trace-only; `scenario.yaml` `arms`, built by `build_arms.py`, recorded in `arms/arms-e0.json`, pinned by `tests/test_t01_arms_e0.py`)

| arm | inherits from | overrides |
|---|---|---|
| L1x | L1 | `traces` → `arms/L1x/traces.yaml` (L1's 17, byte copies, + t18–t21), `requirements` → `arms/L1x/requirements.yaml` |
| L2x | L2 | same shape |
| L3x | L3 | same shape |
| L5x | L5 | same shape; authority events in the typed encoding; gold stays the typed gold (L5's) |
| L6x | L6 | same shape; vendor outputs as plain strings |
| L7x | L7 | same shape |
| L1x-S | L1x | not a file arm: `--arm L1x --input-mode schema-only` (as L1-S was `--arm L1 --input-mode schema-only`) |

Each x-arm names its parent's manifests, schema and gold (the same files, no copies). **No existing arm folder, pinned
file, base scenario file or run folder is edited.** The x-arm folders carry copies of the parent's trace files plus the
four new ones; mutants are not copied: the tests read the parent's `mutants/*.dw`.

### requirements.yaml of the x-arms

Parent's file plus: t18, t19 appended to `security.over_strict_if_denies`; t20, t21 appended to
`security.over_permissive_if_allows` and to `requirements.provenance_source.witnesses`; and a new optional top-level map

```yaml
workflows:
  direct: [t01_valid, t12_second_close_same_session, t13_other_wo_valid]
  reads_vendor: [t18_both_positive, t19_both_positive_vendor_first]
  vendor_negative: [t17_authority_granted_vendor_negative]
```

Every trace named there must be a contract-ALLOW trace of the suite. `load_requirements` keeps accepting files without
the key (every existing requirements file has none).

### Views and classes

- **Views (A0 of Phase 2c):** *first shot* = the naive sample = Sondera-style round 1 (one cache entry; the run records
  `first_shot_shared_with_naive`, expected 20/20 in every replay); *final* = the Sondera-style final policy. Two views of
  20 samples per arm, never 40.
- **Surplus** (this task's definition) = the policy allows **any of t15, t16, t20, t21**: the four contract-deny traces in
  which the vendor's positive record is present. Over scored samples (valid, no replay error).
- **Workflow passed** = the policy allows **every** trace of that workflow's list (`workflows_allowed` per sample).
- **Classes of a surplus policy**, from the 2×2 of (passes `direct`) × (passes `reads_vendor`):

| passes direct | passes reads_vendor | class |
|---|---|---|
| no | no | **loud in both** (fails a positive test in either workflow) |
| no | yes | **silent when the vendor is read** (fails the direct positive tests, passes them once the vendor record is in the history) |
| yes | yes | **silent in both** |
| yes | no | not expected (a policy that needs the vendor record to be *absent*); reported if it occurs, under its own row |

Counts only, per arm and per view: scored, surplus, each class, and the allow count of each of t18–t21. No contrasts, no
intervals beyond the run's own Wilson fields, no interpretation beyond the classes above, no new arms.

### Tooling (domain-agnostic; tests first)

- `pgi.generators.dogwood_inputs.load_requirements`: optional `workflows` (name → traces; every trace must exist and be
  contract-ALLOW), exposed as `Requirements.workflows`, `None` when absent.
- `pgi.runs.temporal_clean.score`: `workflows_allowed` per scored sample (names of workflows whose every trace is
  allowed) when the requirements carry `workflows`. `summarize`: `workflow_counts` (per workflow, scored samples passing
  it). Nothing changes for scenarios without the key.
- `pgi.runs.workflow_classes` (new, zero API): reads the replay folders' `oracle.json`, takes `--surplus-traces` and the
  two workflow names, writes `runs/<stamp>-workflow-classes-<label>/report.{json,md}` with the table above. Same atomic
  folder rule as every run.

### Checks before any replay (tests)

1. Gold agrees with the contract on all 21 traces of every x-arm (6 arms).
2. Every existing weakening is still killed. Base `weak_*.dw` on the untyped x-arms (L1x, L2x, L6x; L3x and L7x without
   `vendorflag`, whose tool does not exist in their schema): differs from gold on ≥ 1 trace, the README's "caught by"
   traces still disagree; in addition `window` allows t20 and `binding` allows t21. Parent mutants on every x-arm:
   `vendor_binding` differs from gold on the parent's recorded kill set plus t20, t21; `borrowed_literal` (L2x, L7x)
   on the parent's kill set plus t18, t19; L5x's `borrowed_literal` is killed by validation, as recorded for L5.
3. The vendor-binding mutant of each x-arm allows t18, t19, t20 and t21 and denies t01.
4. The x-arm folders are exactly the build output; the 2b and 2c records and every pinned file keep their bytes.

### Replay plan (zero API; `claude-sonnet-5-5`, `--intent goal-level`, `--n 20`, `--cache-only`, both generators)

In this order, one run folder each: L1x, L2x, L3x, L5x, L6x, L7x (manifests mode), then L1x with
`--input-mode schema-only` (label `L1x-S`). Then `pgi.runs.workflow_classes` once over the seven folders with
`--surplus-traces t15_vendor_enum_only t16_authority_rejected_vendor_positive t20_authority_expired_vendor_fresh
t21_authority_other_wo_vendor_this_wo --direct direct --reads-vendor reads_vendor`. Each replay must report
`api calls this run: 0`; a non-zero count or a cache-miss error stops the task and is reported as a bug.

Expected identities (checked after the replays, reported if violated): the first 17 traces of every sample keep the
decisions recorded in the Phase 2c (and 2c re-tally) folders, since the policies and the parent traces are byte-identical.

## Runs (filled in by the runs commit)

- L1x, L2x, L3x, L5x, L6x, L7x, L1x-S replay folders: `runs/<stamp>-temporal-clean-t01-goal-level-<arm>`.
- Class report: `runs/<stamp>-workflow-classes-t01-e0`.
