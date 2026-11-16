# Fixture: Dogwood `read_after_login_success` example bundle

Copied verbatim from the Dogwood reference interpreter repository
(`dogwood-docs/examples/read_after_login_success/`, github.com/dogwood-policy/dogwood,
commit `929f49e7305534ac61ef06cf8e47269c596dc851`, 2026-11-12; the bundle itself last changed in
`4ec5e2c0`, 2026-10-14). Dogwood is Copyright Amazon.com, Inc. or its affiliates, Apache-2.0.

Files: `policy.dw`, `schema.cedarschema`, `trace.log`, `expected.out` (the interpreter's own expected
verdict stream). `tests/test_temporal.py` asserts that `pgi.oracle.temporal` reproduces `expected.out`.
Never edit these files; they are the known-answer test for the oracle backend.
