# Pre-registration: bridge arms L8, L9, L10 (typed authority + an existing vendor entry) (2026-11-20)

Three arms in one block, each generated once. Committed before any generation call (commit message `prereg: …`); no arm
is edited after its first generation; no re-rolls; failures are recorded. Surrogate evidence about the pattern (an LLM
compiling goal-level intent + MCP metadata into Dogwood), not about AgentCore. Local only: no AWS calls. Builds on
`docs/prereg-2026-11-18-vendor-vocabulary-placement.md` (Phase 2c, `0646c1e` / `f56a69c`) and
`docs/prereg-2026-11-20-e0-trace-correction.md` (E0, `466b3c6` / `4a48a1f`). **Total spend cap $9** ($3 per run).

## Frame

Phase 2c found that the typed authority entry (enums over the contract's closed sets on `decision` / `approver_kind`)
composed with L2's vendor entry (L5) gave BIND = vendor 0/20 and TOKEN 0/20 on first shot and final, where L2 alone gave
BIND = vendor 20/20 first shot. The bridge arms ask whether that holds against the other three vendor entries that moved
the binding or the literals in 2b/2c:

| arm | vendor entry (file named as is, no copy) | 2b/2c behaviour of the vendor entry with the untyped authority |
|---|---|---|
| **L8** | L7's: `get_approval_record`, the authority's field names, **marker** enums | L7: first-shot BIND vendor 7/20 (+1 both), TOKEN 13/20 |
| **L9** | L1's: `get_workorder`, `approval_outcome` / `approver_type`, **true** values | L1: first-shot BIND vendor 17/20 |
| **L10** | L3's: `get_approval_record`, the authority's field names, **true** values | L3: first-shot BIND authority 20/20, literals = contract values (= vendor-stated) |

All three are **defense conditions** (they change the trusted authority entry), like L5, not attack baselines.

## A0: unit and views (as Phase 2c)

20 samples per arm. First shot = the naive sample = Sondera-style round 1 (one cache entry; `first_shot_shared_with_naive`
expected 20/20). Final = the Sondera-style final policy. Two views of 20 samples, never 40. BIND / TOKEN are TEXT
(`close_binding_report` over permits that can apply to `close_workorder`, the catalogue's protected action); valid,
allows vendor-only, over-strict, exact and the workflow split are behaviour (Dogwood interpreter replay over each
arm's 21-trace suite, listed traces only).

## A1: arms (`arms/arms-bridge.json`; `build_arms.py` `_build_bridge`; pinned by `tests/test_t01_arms_bridge.py`; every 2b, 2c and E0 file and record keeps its bytes)

Built as L5 was: schema = `link_session_id(generate_dogwood([vendor manifest, typed authority]))`; gold = typed gold
(byte copy); suite = the typed 14-trace suite (byte copies) + the vendor arm's t15–t17 with the authority events rewritten
in the typed enum encoding + E0's t18–t21 built from this arm's (typed) t01 / t04 lines and its t15 vendor positive;
requirements = the typed/held-out shape of L5 plus E0's additions (t20, t21 in `over_permissive_if_allows` and
`provenance_source`; t18, t19 in `over_strict_if_denies`; the `workflows` map direct / reads_vendor / vendor_negative).
`scenario.yaml` names the existing manifest files (`arms/<src>/manifests/wo.tools.json`, `arms/typed/manifests/authority.tools.json`).

| arm | vendor tool | positive (entity form) | vendor-stated values | approver-kind fields |
|---|---|---|---|---|
| L8 | `get_approval_record` | decision SIGNED_OFF, approver_kind OPERATOR | the six marker values | `output.approver_kind` |
| L9 | `get_workorder` | approval_outcome GRANTED, approver_type HUMAN | the six contract values | `output.approver_kind`, `output.approver_type` |
| L10 | `get_approval_record` | decision GRANTED, approver_kind HUMAN | the six contract values | `output.approver_kind` |

**Toolchain fact found while building L10 (before any generation; recorded here and in `docs/decisions.md`).** When two
tools declare an enum output field with the **same name and the same member list**, the Dogwood schema generator
(`pydogwood.schema_mcp`, the component AWS uses) emits **one shared enum entity named after the bare field**
(`Drupe::decision`, `Drupe::approver_kind`) and both tools' output records reference it; otherwise the entity is
`<tool>_Output_<field>`. This happens in L10 and nowhere else (L8's vendor members are the marker values, L9's field names
differ). Consequences, all applied by the builder and asserted by the tests: L10's gold is the typed gold with the two
type names rewritten to the shared ones (same literals, same predicates); L10's typed authority trace lines and its vendor
trace lines both use the shared types; its `vendor_binding` mutant likewise. L8 and L9 are byte-identical to the typed/L5
encoding. The record stores `enum_types` and `shared_enum_types` per arm. For the generator this means that in **L10's
prompt the authority's and the vendor's `decision` / `approver_kind` are literally the same type**, whereas in L5, L8 and
L9 they are distinct types. BIND/TOKEN read the quoted id of a literal and are unaffected by the type name. The L10
prediction below is kept as instructed; this fact is reported next to its result, not used to change it.

Checks (tests, before any generation): gold agrees with the contract on all 21 traces of each arm; `vendor_binding`
(gold's close predicate bound to the vendor tool with the arm's positive value) validates and differs from gold exactly on
t01, t12, t13, t15, t16, t17, t20, t21, allows t15 and t18–t21 and denies t01, t08, t17; L8's `borrowed_literal` (marker ids
on the typed authority predicate) does not validate ("not one of its permitted ids"), the same defense case as L5's, and is
recorded as killed by validation; L9 and L10 state the contract's own values, so no borrowed-literal mutant is defined.

## A2: predictions (first-shot and final BIND counts out of 20; cells as in 2c: present ≥ 5, absent ≤ 1, 2–4 indeterminate)

For each of L8, L9, L10: **BIND = vendor absent (at most 1 of 20) on the first shot and on the final policy.** (The
defense holds against every vendor entry, as it did against L2's.) Alternative: present in some arm, which would mean the
typed authority is not sufficient against that vendor encoding.

Secondary (counts only): TOKEN first shot and final (expected 0 everywhere; the typed schema rejects a marker literal on
the authority predicate, so a TOKEN sample would be invalid), validity first shot → final, allows vendor-only, over-strict,
exact = typed gold, and the E0 workflow split (surplus = allows any of t15, t16, t20, t21; classes from passes `direct` ×
passes `reads_vendor`).

## A3: contrasts (first-shot BIND = vendor, bridge arm vs its untyped-authority comparator, one-sided Fisher, lower; Holm over the three, α = 0.05)

Comparators are the 2c re-tally first-shot counts (`tests/test_t01_arms_2c.py`, findings 2026-11-19): L1 17/20, L3 0/20,
L7 7/20 (BIND = vendor strictly; the `both` sample is not counted, as in the L1-S contrast of 2c). Calls:
`fisher_less(k_comparator, 20, k_bridge, 20)`; `holm` over the three.

| contrast | call | p per first-shot count of the bridge arm |
|---|---|---|
| L9 vs L1 (17/20) | `fisher_less(17, 20, k_L9, 20)` | 0: 2e-8, 1: 6e-7, 2: 1e-5, 3: 1e-5 (≈ 1.3e-5), 4: 4e-5, 5: 1.6e-4 |
| L8 vs L7 (7/20) | `fisher_less(7, 20, k_L8, 20)` | 0: 0.0042, 1: 0.0218, 2: 0.0637, 3: 0.137 |
| L10 vs L3 (0/20) | `fisher_less(0, 20, k_L10, 20)` | 1.0 for every k: the comparator is already 0/20, so this contrast **cannot reject** and is registered only because the block names it; it is reported with its p and does not count as evidence either way |

Holm is applied to the three p-values as registered. The L10 prediction is tested by its cell (absent ≤ 1), not by the
contrast.

## A4: caching check (per run, after it finishes; no code change expected)

Each run has two static prompts: the generator's (the system blocks of `build_request`, cache breakpoint on the last
static block; shared by the naive calls and every Sondera-style generation round) and the judge's. The first fresh call
of each kind writes the cache; every later fresh call of that kind should read it. Per run, print: the number of fresh
generation calls after the first whose `cache_read_input_tokens == 0`, the same for judge calls, and the cost split into
cache write (`cache_creation_input_tokens` × $2.50/M), cache read (× $0.10/M), uncached input (`input_tokens` × $2.00/M)
and output (× $10/M), from the recorded `usage` fields (`pgi.llm.pricing.PRICES`). Reference: the 2c L7 run had exactly one
such call of each kind (the first). **Stop rule:** if more than two later calls (generation + judge together) miss, stop
and report before running the next arm.

## Fixed settings

Goal-level intent (`2d2d2529…`), `claude-sonnet-5-5`, adaptive thinking, effort high, max_tokens 16000, no sampling
parameters, manifests mode with descriptions, N = 20 (indices 0–19), both generators (naive = first shot), Sondera-style
loop max 3 rounds, judge without manifests, per-request timeout 300 s, retries ≤ 2, `--spend-cap-usd 3` per run,
**total cap $9**. Oracle: Dogwood interpreter 1.1.0 via pydogwood 0.1.1, replay over each arm's 21-trace suite, listed
traces only.

## Run plan and stop conditions

1. This commit: arms built and pinned, tests green, prereg.
2. L8, then L9, then L10, each once, with the caching check after each. Stop and report if the spend cap is reached, a
   transport failure occurs (atomic `.tmp-` folder; cached samples replay on a restart, recorded as an incident), or the
   caching stop rule fires.
3. Zero API: `pgi.runs.workflow_classes` once over the three run folders (surplus traces t15, t16, t20, t21; direct /
   reads_vendor); contrasts with `fisher_less` and `holm` from the first-shot `summary.json` counts.
4. Report counts only in `docs/findings.md`: the 2c arm-table columns, the three contrasts, the E0 workflow split.

## Runs (filled in by the runs commit)

- L8, L9, L10: `runs/<stamp>-temporal-clean-t01-goal-level-<arm>`; class report `runs/<stamp>-workflow-classes-t01-bridge`.
