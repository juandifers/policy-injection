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
