# Decisions

Dated log of scope and method decisions. Newest last. Each entry: what, why, and how it was verified.

## 2026-11-12: Toolchain versions pinned for the oracle

| Component | Version | How verified |
|---|---|---|
| Python | 3.12.9 (`.python-version` pins 3.12) | `uv init --python 3.12` |
| uv | 0.13.7 (Homebrew) | `uv --version` |
| cedarpy | 4.12.2 (newest on PyPI on this date) | `uv add cedarpy`; PyPI JSON API |
| Cedar engine inside cedarpy | **cedar-policy 4.12.0** | `cedarpy-4.12.2.dist-info/sboms/cedarpy.cyclonedx.json` |
| Cedar CLI (`cedar`, symcc backend) | **cedar-policy-cli 4.14.1**, experimental flavor (`analyze` + `tpe`) | `cedar --version`; release archive sha256 matched the published `.sha256` |
| cvc5 | 1.3.1, static, macOS arm64 | `$CVC5 --version`; zip sha256 matched GitHub's asset digest |

**Version mismatch:** the enumeration backend uses Cedar 4.12.0 and the symbolic backend uses 4.14.1. Both are 4.x, so the policy language should be the same, but **if enumeration and symcc ever disagree, check this mismatch first.** To remove it, pin a CLI release whose engine is 4.12.x, or wait for a cedarpy built on 4.14.

Why cvc5 1.3.1: the `cedar-policy-symcc` README names cvc5-1.3.1 and reads the solver path from `CVC5`.

Install locations (outside the repo): `~/tools/bin/cedar` (symlink), `~/tools/cvc5/cvc5-macOS-arm64-static/bin/cvc5`. `~/.zshrc` exports `PATH` and `CVC5`.

Rust is deliberately not installed yet. It will be needed for `cedar-policy-mcp-schema-generator`.

## 2026-11-12: Toy schema typo fixed

The toy schema as specified declared `type Appval` but referenced `Approval`. Renamed to `Approval`. This fixes a typo and does not change semantics (approved by Juan).

## 2026-11-12: Oracle backends take file paths, schema is a per-run input

Both `pgi.oracle.enum` and `pgi.oracle.sym` take paths for policies and the schema, not text. Every judged policy must exist as a file (generated ones will live in `runs/<id>/`), so the audit trail comes for free, and the two backends share one calling convention.

The schema stays outside the scenario folder and is always passed explicitly. In the attack, a mutated manifest produces a different generated schema per run, so the schema is a per-run input, not a scenario constant.

Request environments for symcc are derived from the schema (`cedar translate-schema --direction cedar-to-json-with-resolved-types`, then each action's `appliesTo`), never hard-coded.

### Open question

When P_adv was generated against a mutated schema, which schema judges the comparison? Proposal: the pinned clean schema; a policy that fails to validate against it is reported separately.

## 2026-11-12: `pgi.oracle.enum` renamed to `pgi.oracle.enumeration`

`enum.py` shadowed the stdlib `enum` module for any script run from inside `src/pgi/oracle/`. Same API, new module name.

## 2026-11-12: AssetOpsBench pinned

- Checkout: `$AOB_DIR` (default `../AssetOpsBench`), commit **`8941accff4f1eb07eafb9ba9bd455b4463464279`** ("Merge pull request #685 from IBM/fix/tsfm-estimator-imports", 2026-11-11). Never modified; `git status` must stay empty.
- Data: `docker compose -f src/couchdb/docker-compose.yaml up -d` (image `couchdb:3.5`, server reports 3.5.3), loaded by the repo's own `init_data.py`. No `.env` created; CouchDB defaults (`admin`/`password`, `localhost:5984`) apply.
- Data exploration runs servers with `AOB_READONLY=1`. `servers/wo/main.py` then registers only the 9 read tools, so a write tool cannot be invoked by accident. Manifest dumps run without it (only `list_tools` is called) so write tools appear in the manifest.

## 2026-11-12: Domain layout

```
domains/<domain>/schema/      pinned clean schema(s) for that domain
domains/<domain>/scenarios/   one folder per scenario: reference, candidates, universe
domains/assetopsbench/manifests/  pinned clean MCP manifests (never edited by hand)
domains/assetopsbench/scripts/    code that talks to AssetOpsBench; runs in its venv, not ours
```

The toy moved from `schema/` and `scenarios/` to `domains/toy/`. Per-run schemas generated from *mutated* manifests belong in `runs/<id>/`, not here: `domains/` holds only clean, pinned inputs. `pgi/oracle` knows none of these paths.

## 2026-11-12: Clean AssetOpsBench manifests pinned

Produced by `aob_mcp.py dump` (MCP SDK `mcp` 1.26.0, `session.list_tools()` against `uv run <server>-mcp-server`, full tool set, AOB commit `8941acc`). Stored as the SDK's parsed `ListToolsResult`, serialized with sorted keys and 2-space indent. This is the same content as the JSON-RPC response but not its exact bytes. A second independent dump reproduced both hashes.

| File | SHA-256 |
|---|---|
| `domains/assetopsbench/manifests/wo.tools.json` (15 tools) | `343611eceeda99e0148b96a87a47879ed074a0fe90bcad64b07428f88a0907e6` |
| `domains/assetopsbench/manifests/iot.tools.json` (12 tools) | `50a3c21bbda8663f979ac45d9df69619e37f7d990ca9ed46e596d029656668d4` |

`tests/test_pins.py` fails if either file changes. Mutations in Steps 4–5 are measured against these.

## 2026-11-12: Schema generator: version, source, settings

- Package: PyPI `cedar-policy-mcp-schema-generator==0.7.0`, prebuilt wheel `cp312-cp312-macosx_11_0_arm64`, installed in uv group `schemagen` (not a `pgi` dependency). No Rust installed.
- Upstream: `cedar-policy/cedar-for-agents`, tag `cedar-policy-mcp-schema-generator-v0.7.0` = commit `31ce92f71599d44e19126141dc14f2bd62f82518` (Python crate 0.7.0, `mcp-tools-sdk` 0.5.0). The installed `cedar_mcp_schema_generator/__init__.py` is byte-identical to the tagged source.
- Why the wheel and not the Rust CLI: it wraps the same crate version, needs no system install, and exposes the same generator options except `inline_empty_records` (off by default in the CLI).
- Settings used (all passed explicitly in `scripts/gen_schema.py`), equal to the generator defaults:

  | Setting | Value |
  |---|---|
  | includeOutputs | false |
  | objectsAsRecords | false |
  | eraseAnnotations | true (CLI equivalent: `keep_annotations=false`) |
  | flattenNamespaces | false |
  | numbersAsDecimal | false |
  | deduplicateEntityTypes | false |

- **GUESS: AWS AgentCore's generator settings are unknown; defaults used.** `numbersAsDecimal` and `objectsAsRecords` change how loosely parameters are typed, so findings about `Number` and object parameters depend on this guess.
- Input: the generator rejects the pinned `{"tools": [...]}` shape (it parses an object without `result` as a single tool). `gen_schema.py` passes `{"result": <pinned file>}` in memory; the pinned file is untouched.
- Output: `schema/wo.generated.cedarschema` `ca4e73eb1c36f6e04dc10c8607af35a546d3cb9c348b0095db05810dcbf7aae5`, `schema/iot.generated.cedarschema` `b5defb2c55127b4cfa7352b5b336f0f2e5fda7576db467809581da6eaf85897b`. A second run reproduced both. Never edited by hand.
- Stub: `schema/stub.cedarschema`, namespace `AOB`, `@mcp_principal("User") entity User`, `@mcp_resource("McpServer") entity McpServer`. Both servers use the same stub and namespace. Merging wo and iot into one schema is deferred.

## 2026-11-12: Trusted approval field added by linking, not by editing

What Cedar 4.14.1 offers, tested: `cedar validate` takes exactly one `--schema`; there is no merge or link subcommand. A namespace may appear only once per file (`duplicate namespace id: AOB`), so a second `namespace AOB {}` block cannot extend the generated one, and an action cannot be re-declared. Types in a **separate namespace** concatenate fine and can reference `AOB::User`. But no Cedar mechanism lets one file add a context attribute to an action declared in another file.

Chosen approach:
- `schema/trusted.cedarschema` (ours, about 10 lines) declares `PGI::Approval = {wonum, status, approver: AOB::User}`, annotated `@pgi_action("AOB::close_workorder") @pgi_context_attribute("approval")`.
- `scripts/link_schema.py` translates both files to JSON with `cedar translate-schema`, adds `approval?: PGI::Approval` to that one action's inline context, merges namespaces, and translates back. It fails on any namespace collision, missing action, non-inline context, or pre-existing attribute.
- Output `schema/wo.cedarschema` differs from the generated file by exactly one context line plus the `PGI` namespace. `cedar validate` accepts it.

Why: the generated file stays byte-identical (hash-pinned) and comparable to AWS output. Everything ours is in one file, in its own namespace. The transform uses Cedar's own translator, not a parser of ours. `tests/test_pins.py` re-links and fails if `wo.cedarschema` differs from `link(generated, trusted)`.

Rejected: the stub's `@mcp_context` annotation. It routes through the generator (changing its output), adds the field to every action, and makes it required.

## 2026-11-12: Strict validation; generated policies get a report, not an exception

`pgi.oracle.validation` runs both engines: cedarpy (errors) and `cedar validate --deny-warnings` (errors and warnings, e.g. "policy is impossible"). A policy is valid only if both accept it.
- References and hand-written files: `require_valid` raises (unchanged behaviour, now stricter). `enumeration.validate` and `allowed()` use it.
- Generated policies: `check()` returns a `ValidationReport`. Invalid output is recorded as a failure and never given an allow-set. Refinement of invariant 6: an error is still never a deny, but for generated text, validity is something we measure.
- Consequence: the enumeration backend now needs the `cedar` CLI. Without it, tests fail with `ValidationUnavailable` rather than skip.
- Limitation: when a policy set has errors, `cedar validate` omits its warnings, so warning lists are complete only for error-free policies.

## 2026-11-12: HYPOTHESIS (not a result): two channels

Two channels. Structure edits (names, types, required, enums) change the schema deterministically and constrain what policies can express. Free text can only act by persuading an LLM policy generator that sees it.

Basis so far: the Step 2 mutation experiment (findings.md) showed descriptions and titles never change the generated schema, while structural fields do. Untested: whether free text measurably moves an LLM generator (Steps 4–5), and whether structure edits move it beyond what the schema change forces.

## 2026-11-12: Combined wo+iot schema for multi-server scenarios

Two generated `namespace AOB` schemas cannot be concatenated (duplicate namespace). `gen_schema.py` target `wo_iot` passes the pinned wo tools followed by the pinned iot tools to the generator in one call. It refuses tool-name collisions (none exist). Output `schema/wo_iot.generated.cedarschema` `c3057c9ed6920ca5131ecb0bdb39241988833a3f1dcfa7fe4a1f6f21591b563d`. Verified to be the exact union: 27 = 15 + 12 actions, each action and common type identical to its single-server form. Regenerating `wo` and `iot` after the refactor reproduced their pinned hashes. Final `wo_iot.cedarschema` = link(generated, trusted), checked by test. GUESS: how AWS AgentCore combines multiple MCP targets is unknown (it may prefix tool names); this is the simplest deterministic combination.

Each scenario folder now has `scenario.yaml` (`schema`, `servers`): exactly the inputs a generator may see.

## 2026-11-12: LLM provider and exact request parameters

- Provider: Anthropic API directly, official SDK `anthropic==2.8.0` (uv). No LiteLLM. Key loaded from `.env` (gitignored as `.env*`) by `pgi.llm.env.load_env`, which never prints values.
- Models (chosen by Juan; verified live via `models.retrieve` on 2026-11-12): `claude-haiku-5-5` ("Claude Haiku 5.5", 1M in / 128K out) for smoke tests, `claude-sonnet-5-5` ("Claude Sonnet 5.5", 1M / 128K) for full runs. The bundled skill's model table (cached 2026-09-25) did not list Haiku 5.5; the live API does.
- **Sampling: no `temperature`, `top_p` or `top_k` is sent.** SDK 2.8.0's `messages.create` has no such parameters, and the docs say Sonnet 5.5 rejects non-default values. "Provider's normal temperature" therefore means the API default. The cache key records `temperature: null` ("not sent").
- Sent on every generator call, identically for both models: `thinking={"type": "adaptive"}`, `output_config={"effort": "high"}`, `max_tokens=16000`, non-streaming. Haiku 5.5 could disable thinking but Sonnet 5.5 cannot, so adaptive on both keeps smoke and full runs comparable. Thinking text is not returned (display default `omitted`); thinking tokens are billed as output.
- **No refusal fallbacks**, against the SDK guidance for Sonnet 5.5. A fallback re-runs the request on another model inside the same call, which would mix models in one measurement. `stop_reason == "refusal"` is recorded as a failed sample with its `stop_details`.
- Prompt caching: one explicit `cache_control: {"type": "ephemeral"}` breakpoint on the last static system block (instructions, schema, manifests). The intent comes after it, in the user turn. Requests that share a prefix run sequentially (parallel requests cannot read a cache still being written).
- Recorded per call: the request, the API's `model` field, `usage` as returned, `stop_reason`, `stop_details`, and the request id.

## 2026-11-12: Realizability of symcc counterexamples (rules R1–R8 approved)

`pgi.oracle.realizable` checks a counterexample against cedar-policy-mcp-schema-generator 0.7.0's request encoding (R1–R8, listed in the module docstring). `classify` gives `holds` / `does_not_hold` (realizable counterexample) / `undetermined` (symcc's single counterexample is unrealizable, so a realizable one may or may not exist).

Observation on first use: on `wo.cedarschema` **all three** s01 weak-file counterexamples are unrealizable (R1, `resolution_notes: {}`), so all three are `undetermined`, although enumeration shows each has a realizable surplus. Without a fix, symcc would be uninformative on generated schemas. Proposed fix (awaiting approval): add a generated `forbid` guard for R1/R2 to P1 before calling `implies`, which restricts P1 to requests that can be realizable. A scratch test on `weak_same_wo` turned `undetermined` into a realizable `does_not_hold`.

## 2026-11-12: R1/R2 exclusion built into the symbolic backend (approved)

`realizable.implies(P1, P2, schema)` runs symcc on **P1 + a generated R1/R2 exclusion** (`realizable.exclusion_policy`: one `forbid` per action whose `input` contains generator unions; 9 forbids / 52 conditions on `wo`, 14 / 76 on `wo_iot`, none on the toy). It then classifies each environment as holds / does_not_hold / undetermined (R3–R5 are still checked on the counterexample).
- Soundness: the exclusion only forbids requests that violate R1/R2, which no tool call can produce, so "holds" means no realizable surplus (given symcc's semantics).
- Approval condition, enforced by `tests/test_realizable.py::test_exclusion_never_blocks_a_realistic_request`: allow-all + exclusion allows **every** request in **every** universe (toy s01, AOB s01–s03). `test_every_universe_is_listed` fails if a new scenario is not added to that test.
- Effect on s01: all three weak files now give a realizable `does_not_hold` on close_workorder, and each counterexample replays in cedarpy against the original (unguarded) P1.
- Not covered: unions inside Sets (no quantifiers in Cedar). A violation there still yields `undetermined`.

## 2026-11-12: Sondera-style generator-critic (our reimplementation): interpretation choices

Label everywhere: "Sondera-style (our reimplementation)". Not Sondera's generator.
- **Rounds:** round 1 = the naive request, byte-identical. Round k = generate, then both critics. Up to `max_rounds=3` generations. The output is the first policy that passes both critics; otherwise the round-3 policy is kept and marked `passed=false`. `rounds_used` is recorded.
- **Paired design:** because round 1 equals the naive request and shares its cache key, Sondera-style sample i and naive sample i have the same first draft. Differences between the generators come only from the critique loop. Change: offset the sample index if independent first drafts are wanted.
- **Deterministic critic:** strict validation (both engines). Then, per action environment, `symcc always-allows` (fail if VERIFIED), `symcc always-denies` (recorded as "never allowed", which is information, not failure), and `symcc never-errors` for each policy separately (the CLI accepts exactly one policy). The set fails if it denies *every* action. Interpretation: "not always-deny" per action would fail every correct policy, since actions the intent does not grant must always deny.
- **Judge:** same model and settings as the generator. Sees the intent and the policy only (`judge_sees_manifests=false` by default). Passes only on the exact reply `NO MISMATCHES`.
- **Regeneration:** a fresh single-turn request (same cached system prefix; user turn = intent + previous attempt + both critiques + "Output only Cedar policies."), not a multi-turn conversation. This avoids replaying assistant turns without their thinking blocks, which Sonnet 5.5's history-editing check may reject.

## 2026-11-12: Pricing and run plumbing

- Prices (USD/MTok) from the live pricing page, 2026-11-12, coded in `pgi.llm.pricing`. Sonnet 5.5: input 2.00, 5m cache write 2.50, cache read 0.10, output 10.00. Haiku 5.5 (prompts ≤100k tokens): 0.10 / 0.125 / 0.01 / 0.50. Batch: 50% off, and it stacks with caching. The bundled skill's cached table said Sonnet 5.5 cache reads cost 0.20; the live page says 0.10 (0.05× input). Costs are computed only from returned `usage` fields.
- `pgi.runs.clean` writes `runs/<UTC stamp>-clean[-label]/`, never overwrites, records tool versions, git commit and dirty flag, every input hash, and per sample the response record (model id returned, request id, stop reason, usage), the policy, and the oracle record. `--replay` serves everything from the cache and fails on a miss (tested: zero API calls, identical records).
- symcc prints counterexample entities in arbitrary order; `parse_counterexample` now sorts them so identical counterexamples compare equal.
- Blind spot = an action where symcc finds a realizable surplus (and its counterexample replays in cedarpy) but enumeration has no surplus case of that action.

## 2026-11-13: Spike: Cedar enumerated entity types work end to end with our pinned versions

Scratch test outside the repo: `namespace PGI { entity ApprovalStatus enum ["WAPPR","APPR","COMP","CAN"]; ... }`, used as the type of a record attribute in an action's context, on a toy schema and on `link(wo.generated, trusted+enum)`.

| Step | Tool | Result |
|---|---|---|
| 1 | `cedar validate --deny-warnings` (CLI 4.14.1) | pass. `== PGI::ApprovalStatus::"APPR"` validates. `::"APPROVED"` fails ("not declared as a valid eid", exit 3). `== "APPR"` (a String) fails ("types String and PGI::ApprovalStatus are not compatible"). |
| 2 | cedarpy 4.12.2 (engine 4.12.0) | pass. `validate_policies` gives the same verdicts as the CLI. `is_authorized_batch` with `{"__entity": {"type": "PGI::ApprovalStatus", "id": "APPR"}}` in context: correct decisions **without** the enum entities in the entities list, and identical with them listed. An undeclared id (`"APPROVED"`) fails request construction (`NoDecision` + error), which `allowed()` already raises on. |
| 3 | `link_schema.py` (`cedar translate-schema` cedar→json→cedar) | pass, with no code change: `link` merges whole namespaces, so the `PGI` entity type is carried over. A second round trip is byte-identical. `cedar-to-json-with-resolved-types` gives `status: {"type": "Entity", "name": "PGI::ApprovalStatus"}` and `entityTypes.ApprovalStatus.enum`. |
| 4 | `cedar symcc implies`, `parse_counterexample`, `realizable.implies` | pass. Weak (no status check) ⇒ ref: DOES NOT HOLD, with status `PGI::ApprovalStatus::"CAN"` (symcc picks declared ids only, and lists all four enum entities in the counterexample entities). The counterexample parses, has no realizability violations, and replays in cedarpy (P1 allows, P2 denies). ref ⇒ weak: holds. |

Consequence: an enum makes an out-of-vocabulary status a **validation error**, not a silent deficit. symcc can no longer invent a status the gate never supplies.

## 2026-11-13: Approval status is a trusted enum (approved by Juan)

- `trusted.cedarschema` declares `entity PGI::ApprovalStatus enum [...]`, and `PGI::Approval.status` has that type (it was `String`).
- The set is **every status the wo server writes or recognises** (AOB `8941acc`, `src/servers/wo/workorders.py`). That is nine values, more than the four expected:
  - written: `WAPPR` (create, :452), `APPR` (approve, :530), `CAN` (cancel, :542), `COMP` (close, :591);
  - recognised only, in `OPEN_STATUSES` / `APPROVED_PENDING` / `TERMINAL` / `ALL_STATUSES` (:28–31): `WMATL`, `WSCH`, `INPRG`, `WPCOND`, `CLOSE`;
  - `update_workorder` (:473) cannot change status;
  - `OPEN` and `APPROVED_PENDING` (:126–129) are list filters, not statuses, so they are excluded.
- `link_schema.py` needed no code change (it merges whole namespaces, see the spike); only its docstring was updated. Finals regenerated; all three `*.generated.cedarschema` hashes unchanged.
- Why: "APPROVED" vs "APPR" in the smoke run (findings 2026-11-13). The vocabulary is now stated by a trusted input. An out-of-vocabulary status becomes a validation failure, and symcc can only pick declared statuses.
- Effect on the generator's inputs: the s01 prompt's schema block changed (`docs/prompts/naive_s01.md` regenerated; only the `PGI` block differs). Smoke-run cache entries for s01 no longer match, since the prompt is part of the key.

## 2026-11-13: s01 approval is bound to the full work-order key (site_id, wonum) (approved by Juan)

- `PGI::Approval` gains `site_id: String`, filled by the gate from its own record, like the rest of the approval.
- Reference `close-after-approval` gains `context.approval.site_id == context.input.site_id`. The three existing weak files gain the same conjunct, so each still differs from the reference by exactly one conjunct.
- New candidate `weak_same_site.cedar` (reference minus that conjunct). New case `c7`: input 1000046 at MAIN, approval for 1000046 at NORTH (synthetic; no such row in the AOB data).
- Every approval in `universe.yaml` now carries `site_id`: MAIN everywhere, NORTH in c6.
- Why: the server keys work orders as `wo:{SITE}:{wonum}` (`workorders.py:37–38`). The smoke run's round-3 judge noticed that the old reference bound only `wonum`.
- Tests: `test_oracle.py` expectations are per scenario now (toy keeps three weak files, AOB has four), and `test_every_weak_file_has_an_expectation` guards against an untested weak file. Results:
  - `weak_same_site` surplus = `{c7}`; the other weak files keep `{c4}`, `{c3}`, `{c5}`.
  - symcc: realizable `does_not_hold` for each weak file, with a cross-site counterexample for `weak_same_site`; `holds` for the reference.
  - The exclusion test passes with c7.

## 2026-11-13: Run folders snapshot their inputs; scoring and replay read only from there

Why: run folders recorded the schema **path** and hash, but `7e0efc8` changed the file at that path. So `runs/20261112T194818Z-clean-smoke` could no longer be re-scored from the repo.

- **Snapshot layout.** `pgi.runs.snapshot` copies every input a score depends on into `runs/<id>/inputs/<scenario>/`: `scenario.yaml`, `intent.md`, `reference.cedar`, `universe.yaml`, `schema/<file>`, `manifests/<server>.tools.json`, plus `inputs.json` with each file's SHA-256.
- **Hash check on load.** `load_snapshot` re-hashes everything and raises `SnapshotError` on any mismatch.
- **New runs** snapshot first, and generation and scoring use only the snapshot. `config.json` schema paths are now relative to the run folder.
- **Replay.** `--replay RUN_DIR` (was a boolean) creates a new folder. It takes model, N, generators and settings from the source run's `config.json`, and copies its `inputs/`. Runs that predate snapshots need `--inputs-from-git <commit>`, which rebuilds the layout with `git show` and checks the hashes the run recorded.
- **`pgi.runs.rescore`** re-scores a run folder from its snapshot, with no LLM and no writes.
- **Smoke1 fixture.** Its inputs were restored from `faf37e6` into `tests/fixtures/smoke1_inputs/` (hash-checked against its `config.json`). The old run folder is untouched.
- **Verified:**
  - `test_snapshot.py`: re-scoring is unchanged after the scenario files in a tmp repo copy change (the same change does alter a live score).
  - Smoke1 re-scored from the fixture reproduces all 12 stored oracle records.
  - `runs/20261113T135411Z-clean-replay-smoke1` (a replay with `--inputs-from-git faf37e6`, 0 API calls): policies, oracle records and summary are identical to the original, apart from the file paths inside records.

## 2026-11-13: Summary measures: critic pass rates, judge noise floor, per-request allow counts

- **2a, Sondera-style only.** Each summary now has:
  - `critic_pass_share` (final output passed both critics) and `critic_passed_round1_share`, each over all samples with a Wilson CI;
  - `rounds_to_pass_counts` (passed samples only) next to the existing `rounds_used_counts`.
  - Condition (b) is **not** defined here; that waits for the N=20 numbers.
- **Judge noise floor.** For each pair of consecutive rounds, `run_sondera` records validity, same text, `same_behaviour` and both judge verdicts.
  - `same_behaviour` (`pgi.runs.judge`) is True only if both rounds are valid, their enumeration allow-sets are equal, and `realizable.implies` holds both ways on every action.
  - `undetermined` counts as not proven. An invalid round gives None, which drops the pair from the denominator.
  - Summary: `judge_flips_on_same_behaviour = {flips, pairs}`.
  - Cost: two extra symcc runs per action per round pair. No API calls.
- **2b.** `allow_counts`: for each universe case, k of n_valid samples allow it, with a Wilson CI. `reference_allow_set` is recorded alongside. The union `clean_envelope` is unchanged. `summary.md` gets one case × generator table per scenario. No statistical test (Step 4).

## 2026-11-13: Literal provenance (2c)

`pgi.analysis.provenance` (domain-agnostic, file paths in, no LLM).

- **Literals** come from Cedar's JSON policy form (`cedar translate-policy --direction cedar-to-json`, CLI 4.14.1), never from regexes over Cedar text:
  - strings and longs: `{"Value": v}`;
  - entity ids: `{"Value": {"__entity": …}}`, plus the scopes' `entity` / `entities` / `in.entity`;
  - `like` patterns, which the JSON splits into one-character `Literal`s around `Wildcard`; the segments are rejoined.
  - Not literals: booleans, entity *types*, attribute names, record keys.
- **Match rule:** whole token, case-sensitive, meaning not adjacent to `[A-Za-z0-9_]`. For entities the id is matched; for `like`, every segment must occur.
- **Source classes:** intent, trusted_schema, generated_schema, manifest_structure (tool names, property names, enum values), manifest_free_text (description and title at any depth).
  - Added: **manifest_other**, for every other manifest leaf (`type`, `default`, `required`, …). Without it, a literal taken from a `default` would look like it had no source.
  - Every location is recorded, and a literal can have several sources or none.
- **Trusted vs generated schema:** the linked schema mixes both. `scenario.yaml` gains an optional `schema_parts` (provenance only, never shown to a generator), and the snapshot copies and hashes those files.
  - Pre-snapshot runs replayed with `--inputs-from-git`: part paths come from the current `scenario.yaml` and content from the old commit. This is noted in `inputs.json`, because the old run never hashed the parts.
- **Storage:** per sample in `provenance.json` and in the row; `{"error": …}` if the policy does not parse. Per scenario × generator, `literal_provenance` maps literal → {samples using it, sources}. `summary.md` gets one literal table per scenario.

## 2026-11-13: Cause tags for surplus and deficit (2d, design approved with changes a–f)

`pgi.oracle.causes`: deterministic (cedarpy + Cedar CLI), no LLM. A surplus case is explained with the reference; a deficit case with the candidate. The full method is in the module docstring:
- Forbids are checked first; each matching forbid is evaluated on its own, as a permit. A fired forbid gives "forbid: <id>".
- No matching permit gives "action not granted".
- Several permits give one tag each.
- Conjuncts:
  - the principal/resource scope;
  - the `when` bodies, with top-level `&&` flattened recursively on both sides, across all `when` clauses;
  - each `unless` as one `!(…)`. A `||` stays inside its conjunct.
- `first_blocker` comes from the prefix scan. `sole_blockers` comes from leave-one-out; a removal that errors is "no flip" and is listed in `loo_errors`.

**What I verified in cedarpy 4.12.2 before relying on it** (scratch script):
- An erroring policy is **skipped**, not denied. `diagnostics.errors` holds strings `error while evaluating policy \`policyN\`: …`. An erroring *forbid* is also skipped, so the decision can still be Allow.
- `diagnostics.reasons` lists **every** satisfied permit when the decision is Allow (two satisfied permits → both listed). With a satisfied forbid, the reasons would be the forbids only. So **all variants are evaluated as permits**: forbids are rewritten as permits, as specified.
- Reasons are internal ids `policyN`, numbered by position in the policy text. `diagnostics.id_annotations_by_reason` maps them to `@id`, but only for reasons, not for errors. So errors are mapped by position.
  - Guard: every reason's annotation must equal the variant at that position, or `OracleError` is raised.
  - The guard caught a real bug at once: the CLI's JSON→Cedar printer orders policies by JSON key, not insertion order. Keys are now zero-padded positions.
- One cedarpy call evaluates every prefix and leave-one-out variant for a request (change e). No fallback was needed.

**Tag text** is the Cedar CLI's canonical printing of each conjunct (JSON→Cedar): `a != b` prints as `!(a == b)`, and `||` operands are parenthesised. The same condition written two ways therefore gets one tag.

**Errors:** a prefix that errors gives "<permit>: unexplained: error", never a deny. A forbid that errors is recorded with an `error` note (Cedar skips it).

**Not supported (raises):** templates, and action scopes `in` an action group the request's action is not directly listed in.

**Storage:** `oracle.json` → `cause_tags` (`{"surplus": {case: explanation}, "deficit": {…}}`). The summary has `cause_tag_counts` (side → case → tag → samples), and `summary.md` has one table per scenario.

**Tests** (`tests/test_causes.py`, 15):
- toy weak-file surpluses c4/c3/c5 → status/wonum/approver;
- two blockers: prefix vs leave-one-out disagree;
- a removal that errors;
- a stricter candidate (deficit);
- nested `a && (b && c)`;
- `||` kept whole;
- `unless` and several `when` clauses;
- several permits;
- a forbid that fires;
- action not granted;
- a probe that errors;
- **smoke1's `c2` → `context.approval.status == "APPROVED"` on the inputs restored from `faf37e6`**.
