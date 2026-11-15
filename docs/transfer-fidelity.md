# Transfer fidelity: where the local surrogate and AWS AgentCore Policy differ

A ledger. Each entry: the field or construct, what our local pipeline does, what AWS documents (with a source),
and whether a local result on it transfers to AgentCore. "Local" means cedar-policy-mcp-schema-generator 0.7.0
with the generator defaults in `pgi.schemagen.CONFIG` (`numbersAsDecimal: False`, `objectsAsRecords: False`),
plus our generators and oracle. AWS's generator settings are not published; the AWS column is what its
documentation states. An entry's "transfers" column is about the schema and the decision, not about whether an
LLM behaves the same on both sides.

| # | Field / construct | Local behaviour (verified) | AWS behaviour (documented) | Transfers? |
|---|---|---|---|---|
| 1 | JSON Schema `number` | Becomes the opaque entity type `AOB::Number` (no attributes, identity only). A policy cannot compare, bound or order it; `3` and `3.0` are different entity ids. Verified on `close_workorder.actual_hours` (docs/findings.md, Step 2 table). | Becomes Cedar `Decimal`: "Decimal is an extension type in Cedar, which does not exactly match IEEE floating point numbers, so numbers will be truncated to the Cedar representation." Conditions use `.lessThan()`, `.greaterThan()` etc. against `decimal("…")` literals with at most 4 decimal places. Source: [Schema constraints, Context table](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/policy-schema-constraints.html). | **No** for any numeric condition. Locally a generator cannot write a bound on hours and the oracle cannot judge one; on AWS it can. Local "no policy can bound hours" is an artefact of `numbersAsDecimal: False`, not a property of AgentCore. Re-run numeric scenarios with `numbersAsDecimal: True` before claiming anything about AWS. |
| 2 | `$ref` / `$defs` in `inputSchema` | Not ignored. 0.7.0 resolves an internal reference: `site_id: {"$ref": "#/$defs/Site"}` with `$defs.Site = {type: string, enum: [MAIN]}` yields `site_id: AOB::close_workorder::Input::Site` and `entity Site enum ["MAIN"]`; an unused `$defs` entry still emits `type Site = String;`. A dangling `$ref` fails generation with `SchemaGeneratorError: Error adding tools: Undefined Reference Type` (checked 2026-11-15 on scratch copies; the pinned `outputSchema`s carry `$defs` but outputs are not read with `includeOutputs: False`). | The Gateway rejected tool schemas with references at target registration: `"Invalid tool schema, $ref is not supported"` ([awslabs/mcp#2442](https://github.com/awslabs/mcp/issues/2442), Pydantic-generated `$defs`/`$ref`). With MCP protocol version 2026-07-28, AWS states input schemas "gain composition keywords (oneOf, anyOf, allOf), conditionals, and internal references ($ref, $defs)" ([How AgentCore Gateway supports the MCP 2026-07-28 spec](https://aws.amazon.com/blogs/machine-learning/how-agentcore-gateway-supports-the-mcp-2026-07-28-spec/)). How Policy's Cedar schema generation treats them under either version is not documented. | **No.** Behaviour differs by protocol version and is undocumented for Policy. Our mutators never introduce `$ref`/`$defs` (`pgi.mutators.edit`), and no manifest containing them is to be sent to AWS. |

## How to add an entry

Verify the local column on a scratch copy (never a pinned file) and quote the AWS column from a primary source
with a link. If a surrogate result depends on an entry marked "No", say so where the result is reported.
