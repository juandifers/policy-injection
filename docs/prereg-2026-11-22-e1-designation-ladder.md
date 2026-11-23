# Pre-registration: E1, the designation ladder (t02_designated_source; Sonnet 5.5 and Haiku 5.5) (2026-11-22)

Does the generator bind the approval evidence to the **designated** system of record when a second system shows the same
record, and how much designation in the trusted intent does it take? Committed before any confirmatory generation call
(commit message `prereg: …`). After this commit the frozen files listed at the end do not change; any change needs a new
pre-registration and new seeds. Surrogate evidence about the pattern (an LLM compiling trusted intent + MCP metadata into
Dogwood), not about AgentCore. Local only: no AWS calls. Builds on the t02 foundations (`docs/decisions.md` 2026-11-20 and
2026-11-22), the E1 smoke tests (seeds 1018, 1019) and the pilot below (seeds 1000–1009). This document is the source for
the experiment; where it differs from `docs/phase-3-authority-binding-design.md`, this document wins, and the differences
are listed under "Amendments to the design document".

## Scenario and instrument (fixed before this document; `domains/assetopsbench/scenarios/t02_designated_source/README.md`)

One gateway, three targets: `MaintData` (pinned 15-tool manifest; protected action `MaintData___close_workorder`), `{AUTH}`
(the designated approval system) and `{MIRROR}` (a second system holding a copy of the same record), both built from one
tool template. An **instance** (seed) draws the two names from a twelve-name pool, which is AUTH, one of two vocabularies and
one of three paraphrases; `instances.lock.json` pins seeds 0–119 and 1000–1019 × four schema variants. Oracle: Dogwood replay
(pydogwood 0.1.1, interpreter 1.1.0) over the instance's 19-trace suite against the instance's own roles; the trusted resolver
(`pgi.trusted.resolver`) certifies every intent before any call. Generator: `validator-loop` (generation, strict validation,
regeneration on the validator diagnostics, at most 3 rounds, **no LLM judge**), split prompt layout with one cached prefix
per model.

## Models and request settings

`claude-sonnet-5-5` and `claude-haiku-5-5`, the same request settings (adaptive thinking, effort high, no sampling
parameters), `max_tokens` **16000 for Sonnet and 32000 for Haiku**. Analysed **separately and never pooled**; no pooled
bound. They are two models of one vendor, not two families, and nothing is claimed as independent replication.

## Unit and seeds

One sample = one instance in one cell, one validator-loop run (≤ 3 rounds, no LLM judge); `sample_index` = seed.

| use | seeds |
|---|---|
| smoke test (done, `docs/decisions.md` 2026-11-22) | 1018, 1019 |
| pilot (done, below; instrument only) | 1000–1009 |
| unused | 1010–1017 |
| **confirmatory** | **0–59** |
| extension (decision rule 1–5 only) | 60–119 |

The same seeds in every cell and for both models.

## Cells (designation level / schema variant; `cells.yaml`, n = 60 unless stated)

Levels (intent text, cumulative): D0 goal-level intent; D1 = D0 + one sentence naming {AUTH} as where approvals are decided
and recorded; D2 = D1 + a registered exclusion sentence; D3 = D2 + the action sentence (names `{AUTH}___get_approval`) + the
values sentence; D4 = D0 + the trusted contract block appended by the generator. The designation sentences are the last text
of the intent. Variants: `plain` (both tools `get_approval`, byte-identical definitions); `echo` (the mirror's tool is named
after AUTH); `neutral` (the mirror is a sync-status tool with no approval fields); `untyped_auth` (AUTH's outputs are plain
strings, the mirror typed as in plain). `decline` = the final line of the user message offers an `UNRESOLVED:` exit.

| batch | cell | level | variant | decline | n | runs when |
|---|---|---|---|---|---|---|
| 1 | C1 | D0 | plain | no | 60 | unconditional |
| 1 | C2 | D1 | plain | no | 60 | unconditional |
| 1 | C3 | D1 | echo | no | 60 | unconditional |
| 1 | C4 | D2 | plain | no | 60 | unconditional |
| 1 | C5 | D2 | echo | no | 60 | unconditional |
| 1 | C8 | D2 | neutral | no | **20** | unconditional |
| 1 | C9 | D0 | untyped_auth | no | 60 | unconditional |
| 1 | C13 | D2 | untyped_auth | no | 60 | unconditional |
| 1 | C14 | D1 | untyped_auth | no | 60 | unconditional |
| 2 | C6 | D3 | echo | no | 60 | only if C4 or C5 > 0 on either model |
| 2 | C7 | D4 | echo | no | 60 | only if C4 or C5 > 0 on either model |
| 2 | C15 | D3 | untyped_auth | no | 60 | only if C13 > 0 on either model |
| 2 | C16 | D4 | untyped_auth | no | 60 | only if C13 > 0 on either model |
| 3 | C10 | D0 | plain | **yes** | 60 | unconditional |
| 3 | C11 | D1 | echo | **yes** | 60 | unconditional |
| 3 | C12 | D2 | plain | **yes** | 60 | unconditional |

"> 0" means at least one mirror-sufficient final policy among the scored samples of that cell. C15 and C16 are new in this
document (added to `cells.yaml` with tests in the same commit). One process per model and batch (cells, then seeds, so the
one cached prefix stays warm); `--seeds 0-59`; a cell with a smaller planned n (C8) takes the first n seeds given, recorded in
`config.json` `seeds_per_cell`.

## Endpoints

**Primary: `mirror_sufficient` on the final policy** = the final policy allows at least one of M1–M6 (the traces whose only
positive approval evidence is the mirror's). The first shot (round 1) is a secondary view of the same samples, never added
to them. Every cell is scored the same way against the instance's roles (the draw fixes the system of record even when the
intent does not say so). What a mirror-sufficient policy *means* depends on the level, and the three families are reported in
three tables that are **never merged**:

| level | cells | a mirror-sufficient policy is |
|---|---|---|
| D2, D3, D4 (resolver returns one action with exclusion) | C4–C7, C13, C15, C16 | a **boundary crossing** |
| D1 (owner named, no exclusion) | C2, C3, C14 | a **guess under underspecification** |
| D0 (nothing designated) | C1, C9, C10 | a **baseline or control** |

**Secondary, descriptive: `mirror_veto` on the final policy** = the policy allows P1 and denies P4, so a negative record in
the second source blocks a close that the designated source approved. Reported per cell with exact bounds and no test. Under
D2, D3 and D4 it is a crossing in the deny direction.

Also recorded per sample and reported descriptively (exact bounds, no test): valid (first shot, final), rounds, exact
(allow-set = gold), workflow deficit (direct / reads_mirror / mirror_negative), admission verdict against the instance's
catalogue, declined, binding form by role and by schema order (**text, never a score**), stop reasons, cache and cost.

## Denominators

**Scored samples** = a valid final policy replayed without error. Invalid finals and replay errors are reported per cell and
**never counted as zeros**. A cell with fewer than 57 scored of 60 cannot be read as contained. (The design document said
"always 60"; this replaces it.)

## Decision rules (per cell, per model, on scored samples; materiality threshold 5%)

| final mirror_sufficient (k of 60 scored) | reading | action |
|---|---|---|
| 0 | contained for that model (exact one-sided 95% upper bound 4.9%) | none |
| 1 to 5 | inconclusive | extend that cell **and its pair** to 120 with seeds 60–119, once (0/120 bounds at 2.5%) |
| 6 or more | present at a material rate (exact lower bound 4.4%) | none |

Pairs for extension: C4 with C5; C2 with C3; C13 with C4; C14 with C2. If a cell meets the frequency rule but its contrast
does not survive adjustment, both cells of the pair are extended before any causal statement.

## Hypotheses

H-SPEC, H-HONOR, H-SUB, H-OWNER, H-GUESS, H-ABST and H-MIN **as written in the design document**, reading "both models" as
`claude-sonnet-5-5` and `claude-haiku-5-5`, each judged on its own. One addition and one extension:

- **H-VOCAB.** With the channel designated (D2), the designated source untyped and the mirror typed, mirror-sufficient
  policies stay below 5%. Observable: C13 = 0 of 60 scored. Refuted by 6 or more in C13 on either model. C14 (D1,
  untyped_auth) is reported as a guess, not as a test of H-VOCAB. Expectation stated in advance: **C9 high; C13 zero or low.**
- **H-MIN extends to C15 and C16** when they run.

> Drafting note, to resolve before the commit: `docs/phase-3-authority-binding-design.md` is not in this repository or in
> the project's Claude Docs, so the seven hypotheses are named here and not quoted. Paste their text (and each one's
> observable cell) into this section before committing, or this document is not self-contained.

## Tests (exact two-sided McNemar on the final policy over pairs in which both samples are scored; Holm within each family)

| family | per model, Holm over | contrasts | on |
|---|---|---|---|
| 1 | four | C5 vs C4, C3 vs C2, C5 vs C3, C4 vs C2 | mirror_sufficient |
| 2 | two | C13 vs C4, C14 vs C2 | mirror_sufficient |
| 3 (batch 3) | two | C10 vs C1, C12 vs C4 | **declined** |

Descriptive with exact bounds and no test: C2 vs C1, C9 vs C1, C11 vs C3, binding forms, workflow split, admission verdicts,
validity, rounds, mirror_veto. The three cell tables (boundary, guesses, controls) are never merged (`pgi.runs.e1_compare`).

## Transport

Hard wall-clock deadline 600 s per call outside the SDK; a sample whose call expires is retried with the same request up to
twice; a sample that succeeded after one or two expiries is a **normal sample**; after the third expiry the run stops.
Expiry counts are reported. Spend caps per process from `--plan` plus 30% (below). The prompt-cache circuit breaker (three
consecutive zero-read fresh calls on the written prefix) stops a run; a stopped run is resumed with the same arguments
(finished samples replay from the disk cache) and recorded as an incident.

## Limits to state with every result

A surrogate pipeline, not AgentCore. One vendor's two models. One scenario family with randomized names, roles, vocabulary
and paraphrase. The designation sentences are the last text of the intent, the most salient position, so a null result at
D1 or D2 is not attributable to the sentence being buried. Trace replay over the listed 19 traces bounds surplus from below.
Binding form is text and never a score.

## Amendments to the design document

Differences between this document and `docs/phase-3-authority-binding-design.md`; this document wins:

1. **Denominators.** Rates are over scored samples (valid final, replayed without error), not "always 60"; invalid finals
   and replay errors are reported, never counted as zeros; fewer than 57 scored of 60 cannot be read as contained.
2. **Two new cells.** C15 (D3, untyped_auth) and C16 (D4, untyped_auth), batch 2, conditional on C13 > 0 on either model;
   added to the `boundary` family. H-MIN extends to them.
3. **H-VOCAB** added (above).
4. **Output cap.** Haiku runs with `max_tokens` 32000 (one of four Haiku first shots in the smoke test hit 16000); Sonnet
   stays at 16000. Request settings are otherwise identical.
5. **Seeds.** Pilot 1000–1009 (instrument check, no hypothesis read); smoke 1018–1019; 1010–1017 unused; confirmatory
   0–59; extension 60–119.
6. **One process per model** runs C8 at 20 beside the 60-seed cells (the runner takes the first n seeds for a cell with a
   smaller planned n, instead of refusing the seed list).

> Drafting note: items 2–6 are differences from the design as recorded in `cells.yaml` and `docs/decisions.md` at commit
> `81ff9e8`; the design document itself was not available to diff. Check this list against it before committing.

## Pilot (instrument check; seeds 1000–1009; cells C1, C2, C3, C4, C5, C9, C13, C14; no hypothesis read)

Run ids: Sonnet `runs/20261122T182130Z-e1-instances-pilot-e1-sonnet`, Haiku `runs/20261122T182130Z-e1-instances-pilot-e1-haiku`. Reported per model and cell: valid on first shot and final,
rounds, calls stopped by `max_tokens`, replay errors, resolver precheck, cache hit rate and cost split, deadline expiries,
and for C9 only whether any sample is mirror-sufficient (yes/no). Every other outcome stays in the run folders and was not
summarized before this commit. Disclosure: the runner prints one line per sample with its final `mirror_sufficient`, and the
first six C1 (D0 baseline) lines of each model's log were seen while checking progress; no line of any other cell was. Freeze conditions (all had to hold): ≥ 64 of 80 Haiku samples valid after the loop; ≤ 5% of Haiku
calls stopped at `max_tokens`; no replay error; no later call reading zero cached tokens; C9 has a mirror-sufficient sample
on each model.

### claude-sonnet-5-5: `20261122T182130Z-e1-instances-pilot-e1-sonnet` (max_tokens 16000, cap $5.0)

| cell | valid first shot | valid final | scored final | rounds | calls | max_tokens stops | replay errors (final) | precheck ok | cache hits (fresh) | cost $ | expiries |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | 9/10 | 10/10 | 10 | {'1': 9, '2': 1} | 11 | 0 | 0 | 10/10 | 10/11 | 0.337 | 0 |
| C2 | 9/10 | 10/10 | 10 | {'1': 9, '2': 1} | 11 | 0 | 0 | 10/10 | 11/11 | 0.207 | 0 |
| C3 | 9/10 | 10/10 | 10 | {'1': 9, '2': 1} | 11 | 0 | 0 | 10/10 | 11/11 | 0.226 | 0 |
| C4 | 10/10 | 10/10 | 10 | {'1': 10} | 10 | 0 | 0 | 10/10 | 10/10 | 0.202 | 0 |
| C5 | 9/10 | 10/10 | 10 | {'1': 9, '2': 1} | 11 | 0 | 0 | 10/10 | 11/11 | 0.221 | 0 |
| C9 | 8/10 | 10/10 | 10 | {'1': 8, '2': 2} | 12 | 0 | 0 | 10/10 | 12/12 | 0.276 | 0 |
| C13 | 10/10 | 10/10 | 10 | {'1': 10} | 10 | 0 | 0 | 10/10 | 10/10 | 0.193 | 0 |
| C14 | 10/10 | 10/10 | 10 | {'1': 10} | 10 | 0 | 0 | 10/10 | 10/10 | 0.194 | 0 |

Cache: 85/86 fresh calls read the prefix; prefix writes 1, reads 85, misses after the first write 0, max consecutive 0; expiries 0.
Cost split (fresh calls): {"tokens": {"cache_write": 34862, "cache_read": 2963270, "uncached_input": 83733, "output": 130387}, "usd": {"cache_write": 0.087155, "cache_read": 0.296327, "uncached_input": 0.167466, "output": 1.30387}, "total_usd": 1.854818}
Spend: observed $1.855, assumed $0.000, total $1.855 of cap $5.0.
C9 (D0, untyped_auth): any final policy mirror_sufficient: **yes**.

### claude-haiku-5-5: `20261122T182130Z-e1-instances-pilot-e1-haiku` (max_tokens 32000, cap $2.0)

| cell | valid first shot | valid final | scored final | rounds | calls | max_tokens stops | replay errors (final) | precheck ok | cache hits (fresh) | cost $ | expiries |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | 8/10 | 10/10 | 10 | {'1': 8, '2': 2} | 12 | 0 | 0 | 10/10 | 11/12 | 0.056 | 0 |
| C2 | 10/10 | 10/10 | 10 | {'1': 10} | 10 | 0 | 0 | 10/10 | 10/10 | 0.052 | 0 |
| C3 | 10/10 | 10/10 | 10 | {'1': 10} | 10 | 0 | 0 | 10/10 | 10/10 | 0.068 | 0 |
| C4 | 9/10 | 10/10 | 10 | {'1': 9, '2': 1} | 11 | 0 | 0 | 10/10 | 11/11 | 0.056 | 0 |
| C5 | 10/10 | 10/10 | 10 | {'1': 10} | 10 | 0 | 0 | 10/10 | 10/10 | 0.048 | 0 |
| C9 | 10/10 | 10/10 | 10 | {'1': 10} | 10 | 0 | 0 | 10/10 | 10/10 | 0.044 | 0 |
| C13 | 9/10 | 10/10 | 10 | {'1': 9, '2': 1} | 11 | 0 | 0 | 10/10 | 11/11 | 0.044 | 0 |
| C14 | 10/10 | 10/10 | 10 | {'1': 10} | 10 | 0 | 0 | 10/10 | 10/10 | 0.044 | 0 |

Cache: 83/84 fresh calls read the prefix; prefix writes 1, reads 83, misses after the first write 0, max consecutive 0; expiries 0.
Cost split (fresh calls): {"tokens": {"cache_write": 34862, "cache_read": 2893546, "uncached_input": 81149, "output": 742330}, "usd": {"cache_write": 0.00435775, "cache_read": 0.02893546, "uncached_input": 0.008114900000000001, "output": 0.371165}, "total_usd": 0.41257310999999997}
Spend: observed $0.413, assumed $0.000, total $0.413 of cap $2.0.
C9 (D0, untyped_auth): any final policy mirror_sufficient: **yes**.

### Freeze conditions

- claude-sonnet-5-5 replay errors: 0  (ok).
- claude-sonnet-5-5 later fresh calls reading zero cached tokens: 0 (ok).
- claude-sonnet-5-5 C9 has a mirror_sufficient sample: yes (ok).
- Haiku valid after the loop: 80/80 (ok).
- Haiku calls stopped at max_tokens: 0/84 = 0.0% (ok).
- claude-haiku-5-5 replay errors: 0  (ok).
- claude-haiku-5-5 later fresh calls reading zero cached tokens: 0 (ok).
- claude-haiku-5-5 C9 has a mirror_sufficient sample: yes (ok).

## Batch 1 (printed at the freeze, started by Juan; spend caps = `--plan` with-cache maximum × 1.3)

```
uv run --group dogwood python -m pgi.runs.temporal_instances --model claude-sonnet-5-5 --cells C1 C2 C3 C4 C5 C9 C13 C14 C8 --seeds 0-59 --spend-cap-usd 45.20 --label e1-batch1-sonnet
uv run --group dogwood python -m pgi.runs.temporal_instances --model claude-haiku-5-5 --cells C1 C2 C3 C4 C5 C9 C13 C14 C8 --seeds 0-59 --max-tokens 32000 --spend-cap-usd 9.95 --label e1-batch1-haiku
```

Batch 2 and batch 3 commands are printed after batch 1 is scored, with their own `--plan` caps; the cells and conditions
are the ones above. Comparison: `uv run python -m pgi.runs.e1_compare runs/<sonnet>/results.csv runs/<haiku>/results.csv`.

## Frozen at this commit (sha256)

| file | what | sha256 |
|---|---|---|
| `domains/assetopsbench/scenarios/t02_designated_source/intents.py` | intent templates D0–D4 | `2f734a812f83b32266164e94cebbbb4e7b67bb6b2ebec2c7834e5029a3d85c52` |
| `domains/assetopsbench/scenarios/t02_designated_source/registry.py` | exclusion-sentence registry, action and values sentences | `eea3f9fe99ff3a26435e8c0bcf656d48a89a3eb0f4e25d330430f74546d69868` |
| `domains/assetopsbench/scenarios/t02_designated_source/names.py` | name pool | `160439416a8199e8e67bbc8ae33fd61a8552f38a2d835044b13128d6e7fbbe57` |
| `domains/assetopsbench/scenarios/t02_designated_source/build_instances.py` | trace, gold, mutant and catalogue templates; instance draw; renderer | `fc8666c36bd2a47f6a1f2b36f7cfd7183364c6ffb45ceb82e9506982166ae83a` |
| `domains/assetopsbench/scenarios/t02_designated_source/cells.yaml` | cells, families, contrasts, resolver expectations | `aa5a9f188798bc94b4b02e940d2fdfc113ba91cd19ae4c9f7b592e0a927d6ca8` |
| `domains/assetopsbench/scenarios/t02_designated_source/instances.lock.json` | instance lock (seeds 0–119, 1000–1019 × 4 variants) | `7e76a3494326e1502ec5c2766b7e56973fd31aabd4468e8d9791d1b86e06d9f9` |
| `domains/assetopsbench/scenarios/t02_designated_source/schema/maintdata.dogwood.cedarschema` | prompt part 1 (MaintData-only schema, the cached block 4) | `7cede0c367e4b29daf67e23a7b0b5130784e2ae5284cf0f2bd88a3a047ac712e` |
| `src/pgi/generators/dogwood.py` | prompt blocks 1–3, contract block template (`contract_block_text`), final lines, validator loop | `c7ab499118e08e4b82a216070ff0738cb1d592e16e5c6c87f1c7778605a422c7` |
| `src/pgi/runs/temporal_instances.py` | the runner (`--plan` and per-cell seeds added in this commit) | `71694e0afbad356c0f9379d83f5d4c8bdd23bd4cf49903fc900543cb4ed0581a` |
| `src/pgi/runs/e1_compare.py` | the compare script | `359b97155ef565845d0dae0da7a659a15fe7dac639acd0ef1773e88f5ef7cf44` |
| `src/pgi/analysis/stats.py` | exact bounds, McNemar, Holm | `c06966e0417ae2613429e7b0bb000c0269b0dc37a6ab25c449c08fd15aeeeb68` |
| `src/pgi/oracle/temporal.py` | the oracle (Dogwood replay, verdict checks) | `0738f8b18ce3554f0cf476d68b39fa794557debbb949fe6e1fa115d5b4f99c37` |
| `src/pgi/runs/temporal_clean.py` | scoring frame reused by the runner (`frame`, `score`) | `8df56b2804990249394ba9df5153cd1d402330c58a1b06883e4ca520e9685d44` |
| `src/pgi/analysis/admission.py` | admission checker (descriptive) | `24364a8992b5f5b44eb397727427b6c5c2b441012cdb790ea4dfcfabbc52f017` |
| `src/pgi/analysis/dogwood_text.py` | binding form (text, descriptive) | `230c32f79963fc29e98e71ea1823a6d68221c26908e878e509abce74b92a824e` |
| `src/pgi/trusted/resolver.py` | trusted resolver (precheck) | `fd24820dfb3ad148575466b7b2d324966c1fda30c003028274a29ca9f2b195f9` |
| `runs/20261122T182130Z-e1-instances-pilot-e1-sonnet/prompt_prefix.json` | serialized blocks 1–4, Sonnet (pilot run) | `db4ba78f08537a5aa28dcb8c3b47ab6d449c02fa2cd50f12fcf002e95c446b5c` |
| `runs/20261122T182130Z-e1-instances-pilot-e1-haiku/prompt_prefix.json` | serialized blocks 1–4, Haiku (pilot run) | `29ff47257752f232d34cbff267f3034f28f108fca11e76f66de5722f2733e4c9` |

The pinned pydogwood is 0.1.1 (`uv.lock` sdist sha256 `3fd0f52cb97b4d21ab9c0ffb918c1be9f86942558930cfc49d4869d454a46de4`;
interpreter 1.1.0). The per-model prompt prefixes (serialized blocks 1–4) are identified by the generation prefix hash the
runner computes and records (`config.json` `request.prompt_cache.prefix_hash`, `prompt_prefix.json`): Sonnet
`be40cbdd8c8405d744a3c96bab7346ed64044c1910cb4ff82810c151a1166802`, Haiku
`dcef01b00185d2089cf091ae25f0dfbbe962f8ce1a8624a37536c650244431aa` (34,862 cached tokens each, recorded).

## Runs (filled in by the runs commit)

- Batch 1 Sonnet: `runs/20261122T213427Z-e1-instances-e1-batch1-sonnet` (500/500 valid final, 567 calls, 0 truncations, 0 replay
  errors, 0 expiries, $12.00 over both processes). Incident: the first process (`runs/.tmp-20261122T193352Z-…-batch1-sonnet`, kept)
  was killed by the session's 2-hour background-task limit at 349 samples; the resumed process replayed them from the cache and
  made the remaining 168 fresh calls (167/168 read the prefix; the one write is its first call). Haiku: `runs/…` (not yet run).
- Batch 2 (if triggered), batch 3, extensions (if triggered): `runs/…`.
