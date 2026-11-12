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
