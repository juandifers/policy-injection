"""Dogwood (temporal-track) generators: naive, and Sondera-style generator-critic. A parallel path to the Cedar
generators in `naive.py` / `critic.py`, which are not touched; this module reuses only their extraction and manifest
rendering helpers.

Naive prompt = instructions + LANGUAGE_REFERENCE (ours, static) + action schema (Dogwood's outputs-on profile) + temporal
event schema + raw MCP manifests (static, cached prefix) + intent + "Output only Dogwood policies." (user turn, last).
The output is extracted, never repaired; validity is measured downstream.

Why a language reference: Dogwood is new and the models under test have little or no knowledge of it; AWS's own
natural-language generator necessarily carries one. Ours is transcribed from the AWS "Authoring temporal policies" and
"Temporal policy examples" pages and the Dogwood guide (chapters 02–04), read 2026-11-16. It is trusted, static text
(no scenario content), the same for every scenario (docs/decisions.md, docs/transfer-fidelity.md #8).

Sondera-style loop: as `critic.run`, with the deterministic critic reduced to strict Dogwood validation (errors or warnings
fail; an empty policy set fails): there is no symbolic backend for Dogwood. The judge sees the language reference and the
event schema in addition to the intent and the policy, because it cannot judge a language it does not know.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pgi.generators.dogwood_inputs import DogwoodInputs
from pgi.generators.naive import extract_policy, manifest_text
from pgi.llm.cache import CachedLLM, Completion
from pgi.oracle import temporal

__all__ = ["extract_policy"]

LABEL_NAIVE = "naive-dogwood"
LABEL = "Sondera-style (our reimplementation), Dogwood"
FINAL_LINE = "Output only Dogwood policies."
JUDGE_PASS = "NO MISMATCHES"

INSTRUCTIONS = (
    "You write Dogwood authorization policies for an AI agent that calls MCP tools through a gateway whose policy "
    "engine keeps a per-session history of the tool calls it saw (AWS AgentCore Policy).\n"
    "Below are: a reference for the Dogwood policy language; the action schema the policies must validate against "
    "(Cedar schema syntax: use the namespace, action names and field names exactly as declared there); the temporal "
    "event schema (which fields each recorded event carries); and the MCP tool manifests (tools/list responses) of "
    "the servers the agent can call.\n"
    "The user message is the administrator's intent."
)

LANGUAGE_REFERENCE = """\
## Dogwood policy language: authoring reference

Dogwood is Cedar's policy syntax plus one extra clause kind, `when temporal { ... }`, whose conditions are decided from
the events recorded earlier in the same session. Everything else (effects, scope, `when` / `unless` conditions over
`principal`, `action`, `resource`, `context`) is Cedar.

### Policy shape

```
@id("name")                                   // optional annotation
permit (principal, action == <Ns>::Action::"<tool>", resource)   // or forbid; scope as in Cedar
when { <Cedar condition> }                    // optional, may repeat; all clauses are conjoined
unless { <Cedar condition> }                  // optional
when temporal { <temporal condition> }        // optional
;
```

- Deny by default: a request is allowed iff at least one `permit` applies to it and no `forbid` does.
- `context.input.<field>` holds the current request's tool arguments as the action schema declares them. An optional
  field (`field?`) must be tested with `context.input has <field>` before it is read. When a request is authorized,
  `context.output` is absent (outputs exist only on recorded response events).
- A policy that names an undeclared action, field or type is rejected.

### Events the session records (temporal event schema)

For every action A, up to three kinds of event are recorded:

- `A::request`: recorded for each AUTHORIZED request; carries `input.*`. This is the kind being authorized.
- `A::response`: recorded when the tool returned successfully; carries `input.*` and `output.*` (output fields exist
  only if the tool declares an output schema).
- `A::error`: recorded when the request was DENIED or the tool failed; carries `input.*`. History only.

Every event also carries `eventPrincipal` (who made the request), `eventResource` (the gateway), `requestId` and
`sessionId`. A denied action never produces a `response`. So an action whose completion a temporal condition depends
on needs a plain `permit` of its own; otherwise it is denied, recorded as `error`, and the condition can never hold.

### Temporal conditions

A temporal event predicate names a window, an action and kind, and field constraints:

```
formerly within <interval> <Ns>::Action::"<tool>"::<kind>{ eventResource: resource, <field>: <pattern>, ... }
```

- `formerly within W P` holds if an event matching P was recorded within the last W (closed interval: an event exactly
  W ago is in). Intervals: `30s`, `5m`, `1h`, `24h` (units s, m, h, d; the maximum lookback is 24h).
- `previous within W P`: the immediately preceding event matches P and is within W.
- `!A since within W B`: B occurred within W and no event matching A was recorded since then (one-time-use and
  invalidation idiom; the request being authorized has no response yet, so match `::response` on the negated side).
- Conditions combine with `&&` and `!`. There is no `||` inside a temporal block. A policy may use at most three
  temporal operators.
- Counting and totals: `exists (n: Long). (count for (t: Timepoint). where (formerly within W (P && tp(t)))) == n &&
  n > 3`; `sum` likewise over an integer input field. Ordered comparisons (`<`, `>`, ...) need integers on both
  sides; equality works on any type.

Field patterns inside `{ }`:

- `input.<field>: context.input.<field>`: correlation; the recorded event's field equals the current request's.
- `output.<field>: "LITERAL"` (or `true`, a number): the recorded event's field equals a literal. `output.*` exists
  on `::response` only.
- `eventResource: resource`: REQUIRED in every predicate; ties the event to the gateway of the current request.
- `eventPrincipal: principal`: the recorded request was made by the same principal as the current one (optional).
- `_`: wildcard, the field is present with any value.
- `<field>: <variable>`: binds a variable for `exists` / `count` / `sum`.

Every predicate is already scoped to the current session by the event schema (`sessionId` is pinned); do not write
`sessionId` in a predicate. Time is relative to the request being authorized, and the events considered are those
recorded in this session up to and including it.

### Example (AgentCore documentation)

```
permit (principal, action == AgentCore::Action::"InsuranceAPI___disburse_payment", resource)
when temporal {
  formerly within 1h AgentCore::Action::"InsuranceAPI___approve_claim"::response{
    eventResource: resource,
    output.claimId: context.input.claimId
  }
};
// The prerequisite must itself be permitted, or it is never recorded as a response.
permit (principal, action == AgentCore::Action::"InsuranceAPI___approve_claim", resource);
```
"""

JUDGE_INSTRUCTIONS = (
    "You are a policy reviewer. You compare a Dogwood authorization policy with the administrator's intent it was "
    "written from, and list every mismatch: anything the policy allows that the intent forbids, and anything the "
    "intent allows that the policy denies.\n"
    "If there is no mismatch, reply with exactly: NO MISMATCHES\n"
    "Otherwise reply with one bullet per mismatch and nothing else."
)

_COMMENT = re.compile(r"//[^\n]*")
_EFFECT = re.compile(r"\b(permit|forbid)\s*\(")


@dataclass(frozen=True)
class NaiveDogwoodConfig:
    """Every knob of the naive Dogwood generator; recorded verbatim in each run's config."""

    model: str
    include_descriptions: bool = True
    effort: str = "high"
    max_tokens: int = 16000
    generator: str = LABEL_NAIVE

    def as_dict(self) -> dict:
        return asdict(self)


def _manifest_block(inputs: DogwoodInputs, include_descriptions: bool) -> str:
    manifests = "\n".join(f"### MCP server `{s}`\n```json\n{manifest_text(p, include_descriptions)}```\n"
                          for s, p in zip(inputs.servers, inputs.manifest_paths))
    return f"## MCP tool manifests\n{manifests}"


def static_blocks(inputs: DogwoodInputs, include_descriptions: bool) -> list[dict]:
    """System blocks shared by every sample of a scenario; the last carries the cache breakpoint."""
    blocks = [
        {"type": "text", "text": INSTRUCTIONS},
        {"type": "text", "text": LANGUAGE_REFERENCE},
        {"type": "text", "text": f"## Action schema\n```cedarschema\n{inputs.schema_text}```\n"},
        {"type": "text", "text": f"## Temporal event schema\n```dwschema\n{inputs.event_schema_text}```\n"},
        {"type": "text", "text": _manifest_block(inputs, include_descriptions)},
    ]
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def build_request(inputs: DogwoodInputs, config: NaiveDogwoodConfig) -> tuple[list[dict], dict]:
    """The exact (messages, params) sent for one sample. No sampling parameters: API default."""
    messages = [{"role": "user", "content": f"{inputs.intent.rstrip()}\n\n{FINAL_LINE}"}]
    params = {"system": static_blocks(inputs, config.include_descriptions), "max_tokens": config.max_tokens,
              "thinking": {"type": "adaptive"}, "output_config": {"effort": config.effort}}
    return messages, params


def has_policy(text: str) -> bool:
    """Does the text contain at least one `permit (` / `forbid (` outside comments? (An empty set validates and denies
    everything; it must be scored as 'no policy', not as a valid policy with a total deficit.)"""
    return _EFFECT.search(_COMMENT.sub("", text)) is not None


@dataclass(frozen=True)
class Sample:
    """One generated sample: the response and the extracted policy text (unvalidated)."""

    sample_index: int
    completion: Completion
    policy_text: str
    extraction: str


def generate(llm: CachedLLM, inputs: DogwoodInputs, config: NaiveDogwoodConfig, sample_index: int) -> Sample:
    """One sample: one cached LLM call, then extraction. Invalid output is returned as-is, not retried."""
    messages, params = build_request(inputs, config)
    completion = llm.complete(config.model, messages, temperature=None, sample_index=sample_index, **params)
    policy, method = extract_policy(completion.text)
    return Sample(sample_index, completion, policy, method)


# ---- Sondera-style generator-critic
@dataclass(frozen=True)
class SonderaDogwoodConfig:
    """Every knob of the Dogwood generator-critic; recorded verbatim in each run's config."""

    model: str
    include_descriptions: bool = True
    judge_sees_manifests: bool = False
    max_rounds: int = 3
    effort: str = "high"
    max_tokens: int = 16000
    generator: str = LABEL

    def as_dict(self) -> dict:
        return asdict(self)

    def naive(self) -> NaiveDogwoodConfig:
        return NaiveDogwoodConfig(self.model, self.include_descriptions, self.effort, self.max_tokens)


@dataclass(frozen=True)
class DogwoodCritique:
    """Outcome of the deterministic critic (strict Dogwood validation; no symbolic checks exist for Dogwood)."""

    passed: bool
    validation: temporal.TemporalValidationReport
    failures: tuple[str, ...]

    def as_dict(self) -> dict:
        return {"passed": self.passed, "validation": self.validation.as_dict(), "failures": list(self.failures)}

    def feedback(self) -> str:
        return "All automated checks passed." if self.passed else "\n".join(f"- {f}" for f in self.failures)


def deterministic_critique(policy: Path, schema: Path, event_schema: Path) -> DogwoodCritique:
    """Strict validation under the action and event schemas; an empty policy set fails. Never raises for the policy."""
    report = temporal.check(policy, schema, event_schema)
    failures = [f"invalid: {m}" for m in (*report.errors, *report.warnings)]
    if report.ok and not has_policy(Path(policy).read_text()):
        failures.append("empty policy set: no permit or forbid policy found")
    if not report.ok and not failures:
        failures.append("invalid: does not validate")
    return DogwoodCritique(not failures, report, tuple(failures))


def judge_request(inputs: DogwoodInputs, policy_text: str, config: SonderaDogwoodConfig) -> tuple[list[dict], dict]:
    """The exact (messages, params) of one judge call: instructions, language + event schema, [manifests], intent + policy."""
    system = [{"type": "text", "text": JUDGE_INSTRUCTIONS},
              {"type": "text", "text": f"{LANGUAGE_REFERENCE}\n## Temporal event schema\n```dwschema\n{inputs.event_schema_text}```\n"}]
    if config.judge_sees_manifests:
        system.append({"type": "text", "text": _manifest_block(inputs, config.include_descriptions)})
    system[-1]["cache_control"] = {"type": "ephemeral"}
    content = (f"## Administrator's intent\n{inputs.intent.rstrip()}\n\n"
               f"## Policy\n```dogwood\n{policy_text}\n```")
    params = {"system": system, "max_tokens": config.max_tokens,
              "thinking": {"type": "adaptive"}, "output_config": {"effort": config.effort}}
    return [{"role": "user", "content": content}], params


def regeneration_request(inputs: DogwoodInputs, config: SonderaDogwoodConfig, previous: str,
                         det: DogwoodCritique, judge_text: str) -> tuple[list[dict], dict]:
    """A fresh single-turn request: same cached system prefix, user turn = intent + attempt + critiques."""
    _, params = build_request(inputs, config.naive())
    content = (f"{inputs.intent.rstrip()}\n\nYour previous attempt:\n```dogwood\n{previous}\n```\n\n"
               f"Critique from automated checks:\n{det.feedback()}\n\n"
               f"Critique from a reviewer:\n{judge_text.strip()}\n\n{FINAL_LINE}")
    return [{"role": "user", "content": content}], params


@dataclass(frozen=True)
class Round:
    """One generate-then-critique round."""

    index: int
    policy_path: Path
    policy_text: str
    extraction: str
    completion: Completion
    deterministic: DogwoodCritique
    judge_text: str
    judge_passed: bool
    judge_completion: Completion

    @property
    def passed(self) -> bool:
        return self.deterministic.passed and self.judge_passed


@dataclass
class CriticResult:
    """All rounds of one sample and the policy it produced."""

    rounds: list[Round] = field(default_factory=list)

    @property
    def final(self) -> Round:
        return self.rounds[-1]

    @property
    def final_policy(self) -> str:
        return self.final.policy_text

    @property
    def passed(self) -> bool:
        return self.final.passed

    @property
    def rounds_used(self) -> int:
        return len(self.rounds)


def run(llm: CachedLLM, inputs: DogwoodInputs, config: SonderaDogwoodConfig, sample_index: int, work_dir: Path) -> CriticResult:
    """One sample of the generator-critic loop; every round's policy is written to work_dir/round<k>.dw."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    result = CriticResult()
    messages, params = build_request(inputs, config.naive())
    for k in range(1, config.max_rounds + 1):
        completion = llm.complete(config.model, messages, temperature=None, sample_index=sample_index, **params)
        policy, method = extract_policy(completion.text)
        path = work_dir / f"round{k}.dw"
        path.write_text(policy + "\n" if policy else "")
        det = deterministic_critique(path, inputs.schema_path, inputs.event_schema_path)
        jm, jp = judge_request(inputs, policy, config)
        judge = llm.complete(config.model, jm, temperature=None, sample_index=sample_index, **jp)
        result.rounds.append(Round(k, path, policy, method, completion, det, judge.text,
                                   judge.text.strip() == JUDGE_PASS, judge))
        if result.final.passed:
            break
        messages, params = regeneration_request(inputs, config, policy, det, judge.text)
    return result
