"""Sondera-style generator-critic (our reimplementation of Sondera's published design; NOT Sondera's generator).

Up to `max_rounds` rounds. Round 1 generates exactly as the naive generator does. Each round's policy goes to:
  1. a deterministic critic: strict validation, then symcc per action (never errors, not always-allow),
     and a check that the set does not deny every action;
  2. an LLM judge given the intent and the policy (and the manifests only if `judge_sees_manifests`).
If both pass, that policy is the output. Otherwise the next round regenerates from a single fresh user turn
holding the intent, the previous attempt and both critiques. After the last round the last attempt is kept
and marked as not passed.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cedarpy

from pgi.generators.inputs import ScenarioInputs
from pgi.generators.naive import FINAL_LINE, NaiveConfig, build_request, extract_policy, manifest_text
from pgi.llm.cache import CachedLLM, Completion
from pgi.oracle import sym, validation

LABEL = "Sondera-style (our reimplementation)"
JUDGE_INSTRUCTIONS = (
    "You are a policy reviewer. You compare a Cedar authorization policy with the administrator's intent it "
    "was written from, and list every mismatch: anything the policy allows that the intent forbids, and "
    "anything the intent allows that the policy denies.\n"
    "If there is no mismatch, reply with exactly: NO MISMATCHES\n"
    "Otherwise reply with one bullet per mismatch and nothing else."
)
JUDGE_PASS = "NO MISMATCHES"


@dataclass(frozen=True)
class SonderaConfig:
    """Every knob of the generator-critic; recorded verbatim in each run's config."""

    model: str
    include_descriptions: bool = True
    judge_sees_manifests: bool = False
    max_rounds: int = 3
    effort: str = "high"
    max_tokens: int = 16000
    generator: str = LABEL

    def as_dict(self) -> dict:
        """JSON-ready form."""
        return asdict(self)

    def naive(self) -> NaiveConfig:
        """The naive config whose request round 1 reuses."""
        return NaiveConfig(self.model, self.include_descriptions, self.effort, self.max_tokens)


@dataclass(frozen=True)
class DeterministicCritique:
    """Outcome of the deterministic critic for one policy file."""

    passed: bool
    validation: validation.ValidationReport
    failures: tuple[str, ...]
    never_allowed: tuple[str, ...]  # actions the set always denies (information, not a failure)

    def as_dict(self) -> dict:
        """JSON-ready form."""
        return {"passed": self.passed, "validation": self.validation.as_dict(),
                "failures": list(self.failures), "never_allowed": list(self.never_allowed)}

    def feedback(self) -> str:
        """Text fed back to the generator."""
        lines = ["All automated checks passed."] if self.passed else [f"- {f}" for f in self.failures]
        if self.validation.ok:
            lines.append("Actions this policy never allows: " + (", ".join(self.never_allowed) or "none"))
        return "\n".join(lines)


def _single_policies(text: str) -> list[tuple[str, dict]]:
    """Each static policy as its own one-policy JSON set, labelled by @id when present."""
    doc = json.loads(cedarpy.policies_to_json_str(text))
    out = []
    for pid, pol in sorted(doc.get("staticPolicies", {}).items()):
        label = (pol.get("annotations") or {}).get("id", pid)
        out.append((label, {"staticPolicies": {pid: pol}, "templates": {}, "templateLinks": []}))
    return out


def deterministic_critique(policy: Path, schema: Path) -> DeterministicCritique:
    """Strict validation, then symcc sanity per action. Never raises for problems in the policy."""
    report = validation.check(policy, schema)
    if not report.ok:
        failures = [f"invalid: {m}" for m in (*report.errors, *report.warnings, *report.cedarpy_errors)]
        return DeterministicCritique(False, report, tuple(failures or ["invalid: does not parse"]), ())
    text = Path(policy).read_text()
    failures, never = [], []
    envs = sym.environments(schema)
    singles = _single_policies(text)
    if any(True for _ in json.loads(cedarpy.policies_to_json_str(text)).get("templates", {})):
        failures.append("templates are not supported; write static policies only")
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for i, (label, doc) in enumerate(singles):
            path = Path(tmp) / f"p{i}.json"
            path.write_text(json.dumps(doc))
            files.append((label, path))
        for env in envs:
            if sym.property_in(env, "always-allows", policy, schema) == sym.VERIFIED:
                failures.append(f"always allows every request for {env.action}")
            if sym.property_in(env, "always-denies", policy, schema) == sym.VERIFIED:
                never.append(env.action)
            for label, path in files:
                if sym.property_in(env, "never-errors", path, schema, policy_format="json") != sym.VERIFIED:
                    failures.append(f"policy {label!r} can raise a runtime error for {env.action}")
    if len(never) == len(envs):
        failures.append("denies every request for every action")
    return DeterministicCritique(not failures, report, tuple(failures), tuple(never))


def judge_request(inputs: ScenarioInputs, policy_text: str, config: SonderaConfig) -> tuple[list[dict], dict]:
    """The exact (messages, params) of one judge call."""
    system = [{"type": "text", "text": JUDGE_INSTRUCTIONS}]
    if config.judge_sees_manifests:
        manifests = "\n".join(f"### MCP server `{s}`\n```json\n{manifest_text(p, config.include_descriptions)}```\n"
                              for s, p in zip(inputs.servers, inputs.manifest_paths))
        system.append({"type": "text", "text": f"## MCP tool manifests\n{manifests}", "cache_control": {"type": "ephemeral"}})
    content = (f"## Administrator's intent\n{inputs.intent.rstrip()}\n\n"
               f"## Policy\n```cedar\n{policy_text}\n```")
    params = {"system": system, "max_tokens": config.max_tokens,
              "thinking": {"type": "adaptive"}, "output_config": {"effort": config.effort}}
    return [{"role": "user", "content": content}], params


def regeneration_request(inputs: ScenarioInputs, config: SonderaConfig, previous: str,
                         det: DeterministicCritique, judge_text: str) -> tuple[list[dict], dict]:
    """A fresh single-turn request: same cached system prefix, user turn = intent + attempt + critiques."""
    _, params = build_request(inputs, config.naive())
    content = (f"{inputs.intent.rstrip()}\n\nYour previous attempt:\n```cedar\n{previous}\n```\n\n"
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
    deterministic: DeterministicCritique
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


def run(llm: CachedLLM, inputs: ScenarioInputs, config: SonderaConfig, sample_index: int, work_dir: Path) -> CriticResult:
    """One sample of the generator-critic loop; every round's policy is written to work_dir/round<k>.cedar."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    result = CriticResult()
    messages, params = build_request(inputs, config.naive())
    for k in range(1, config.max_rounds + 1):
        completion = llm.complete(config.model, messages, temperature=None, sample_index=sample_index, **params)
        policy, method = extract_policy(completion.text)
        path = work_dir / f"round{k}.cedar"
        path.write_text(policy + "\n" if policy else "")
        det = deterministic_critique(path, inputs.schema_path)
        jm, jp = judge_request(inputs, policy, config)
        judge = llm.complete(config.model, jm, temperature=None, sample_index=sample_index, **jp)
        result.rounds.append(Round(k, path, policy, method, completion, det, judge.text,
                                   judge.text.strip() == JUDGE_PASS, judge))
        if result.final.passed:
            break
        messages, params = regeneration_request(inputs, config, policy, det, judge.text)
    return result
