# pgi: policy-generation injection

Research prototype. Results will steer the plan, so this file holds what stays true. Evolving decisions live in `docs/decisions.md`; results live in `docs/findings.md`.

## The question

LLM pipelines now compile natural-language intent plus MCP tool metadata into authorization policies (Cedar) for agents. Examples: AWS AgentCore Policy, and Sondera-style generator-critic loops.

Can an attacker who controls lower-trust text make the generator emit a policy that:

- (a) is more permissive than its output on clean inputs,
- (b) still passes the generator's own checks, and
- (c) lets an attacker-chosen action actually execute?

The defense under study is a two-channel compiler:

- Compiler A reads only trusted inputs.
- Compiler B reads untrusted text and may only add `forbid` rules.
- An admin-authored Ceiling bounds A.

Framing: agent security is a systems problem. The LLM is untrusted and enforcement is deterministic and outside it. If a policy compiler reads attacker-writable text, the attacker co-authors the policy.

## Threat model

- **Attacker controls:** MCP server metadata (descriptions, parameter names, types and enums, extra fields), possibly changed after approval. Also policy-corpus documents, and text laundered into admin prompts.
- **Attacker never controls:** the authenticated trusted channel (admin intent, approved plans, the Ceiling).
- **Out of scope:** a malicious administrator.

## Vocabulary (use these terms exactly)

- **request**: one concrete (principal, action, resource, context) tuple.
- **allow-set(P)**: the requests in a universe that policy P allows.
- **reference (P_ref)**: hand-written least-privilege policy for a scenario. It is contestable, so it needs a written derivation.
- **surplus**: allow-set(P) minus allow-set(P_ref). Is P wrong?
- **clean envelope**: union of allow-sets over N clean generations.
- **expansion**: allow-set(P_adv) minus the clean envelope. Did the attack cause it?
- **generation instance**: (trusted intent, tool manifest, schema) → policy. This is the unit of the probe and attack experiments, not an agent episode.
- **oracle**: deterministic judge comparing two policies.
  - Enumeration (cedarpy, over listed requests) gives counts.
  - Symbolic (`cedar symcc`, over all worlds) gives proofs and counterexamples.
- **gate**: runtime enforcement of one policy on one request. It is not the oracle.
- **mutator**: edits untrusted inputs.
  - **probe**: benign edits; measures requests newly denied.
  - **attack**: adversarial edits; measures requests newly allowed.
- **Ceiling**: admin bound that P_A must imply.

## Pipeline shape

```
trusted inputs ─────────────────────────────┐
untrusted manifest ─→ schema generator ─→ policy generator ─→ candidate P ─→ oracle ─→ surplus / expansion
      ↑ mutator                     (naive · critic · hosted)       │
                                                                    └─→ gate on a real agent run
defense: Compiler A (trusted only) + Compiler B (forbid-only) ─→ P_final ⊑ P_A ⊑ Ceiling
```

## Invariants (ask before breaking any)

1. **No LLM inside the oracle or the gate.** Anything an LLM touches can be injected.
2. **Domain-agnostic core.** The oracle, generators and mutators know nothing about a specific benchmark. Domain material lives in scenario folders (schema, intent, reference, universe, candidates).
3. **Generators are pure.** Files in, policy text out. Every LLM call goes through the on-disk cache, keyed by model, prompt, temperature and sample index.
4. **Trusted and untrusted inputs stay separated in code.** Nothing that feeds a trusted compiler accepts an untrusted field. That includes the schema unless it is pinned.
5. **Compare behavior, never policy text.** Use allow-sets or symbolic implication.
6. **Errors are not denies.** Any authorization or validation error fails loudly.
7. **Say which oracle backs a claim.** Enumeration covers only the listed worlds; symcc covers all of them.
8. **Generation is stochastic.** Sample N, report rates with intervals, and never conclude from one sample.
9. **Experiments write to `runs/<id>/` and are never overwritten.** Each run records input hashes, model id and version, and config. Every reported number traces to a run folder.

## Tooling

- Python ≥ 3.12, `uv`, `pytest`. Run tests with `uv run pytest`.
- `cedarpy` for concrete evaluation.
- `cedar symcc` for symbolic analysis: Cedar CLI built with the `analyze` feature, with `CVC5` pointing to a cvc5 binary.
- `cedar-policy-mcp-schema-generator`: MCP tool manifests to a Cedar schema, the same component AWS uses.
- `dogwood` CLI (validate, lower, replay) for the later stateful phase.
- Third-party APIs move fast. Check installed source or `--help` before relying on a signature, and record what you verified in `docs/decisions.md`.

## Repo layout

```
src/pgi/oracle/              domain-agnostic oracle; no LLM calls; takes file paths only
  enumeration.py             cedarpy over a listed universe: load_universe, validate, allowed, surplus, expansion
  sym.py                     `cedar symcc implies` per schema-derived environment; parse_counterexample
domains/<domain>/schema/     pinned clean schema(s), passed explicitly (per-run schemas go in runs/<id>/)
domains/<domain>/scenarios/<sNN_name>/   reference.cedar, candidate *.cedar, universe.yaml (stable case ids)
domains/toy/                 hand-written toy schema + s01
domains/assetopsbench/
  manifests/                 pinned clean MCP list_tools dumps (hash-pinned; never edit)
  schema/                    stub.cedarschema (ours) -> *.generated.cedarschema (generator, hash-pinned)
                             + trusted.cedarschema (ours) -> wo.cedarschema (linked final)
  scripts/                   aob_mcp.py (runs in $AOB_DIR's venv), gen_schema.py, link_schema.py
tests/test_oracle.py         oracle contract, parametrized over toy and assetopsbench s01
tests/test_pins.py           pinned manifests and generated schemas; final == link(generated, trusted)
docs/                        decisions.md (dated), findings.md (run ids)
```

Run tests with `uv run pytest`. Symbolic tests skip unless `cedar` (with `symcc`) is on PATH and `$CVC5` is set.
AssetOpsBench lives outside the repo at `$AOB_DIR` (default `../AssetOpsBench`, never modified). Generator scripts need `uv run --group schemagen`.

## Substrates (current choice, may change)

- AssetOpsBench (IBM, MCP-native): end-to-end runs and the multi-server, cross-trust setting.
- A second domain with a third-party policy document may be added at the policy level.
- Benchmark choice is an open question, which is one more reason to keep the core domain-agnostic.

## Working with me (Juan)

- I'm learning while building. Before a new component, give me 2–3 sentences on what it does and why it exists; after it, say how it connects. Skip basics I already know.
- Work in small, reviewable steps. Stop at the agreed scope and commit at each green checkpoint.
- For anything in the measurement path, write the tests first and show them to me.
- Text diagrams and step-by-step traces help me more than long prose.
- If you're unsure about an API or a research claim, say so. Never guess silently.
- Ask before:
  - system-level installs;
  - changing scenario semantics or reference policies;
  - anything touching a cloud account. AWS testing must use my own account only; any finding is reported to AWS within 24 hours of finishing testing; never test outbound against other targets.

## Research hygiene

- Keep two findings apart: baseline over-permission (no attacker) and attack-induced expansion.
- An attack on our reimplementation of a design is evidence about the pattern, not proof that the shipping product is vulnerable. Label each generator accordingly.
- Log every scope or method decision in `docs/decisions.md` with the date and reason. Results go in `docs/findings.md` with run ids.

## Current focus

<!-- Update when the phase changes. -->
Phase A: Cedar access layer. Oracle, then schema, clean baseline, channel probe, attack, defense.
Phase B (later): Dogwood stateful policies.
