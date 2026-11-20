"""t02_designated_source (Phase 3, E1): seeded instance generator. Deterministic, no LLM.

    uv run --group dogwood python domains/assetopsbench/scenarios/t02_designated_source/build_instances.py --base          # schema/ (committed)
    ... --render 0 1000 --variants plain echo                                                                             # instances/ (not committed)
    ... --lock            # instances.lock.json over seeds 0-119 and 1000-1019 x four variants (committed)
    ... --check           # rebuild the lock's instances into a temp folder and compare every hash

The world (README.md): one gateway `wo` with three targets. `MaintData` is the pinned 15-tool maintenance manifest, unchanged
(domains/assetopsbench/manifests/wo.tools.json). {AUTH} is the approval system of record; {MIRROR} is a second system holding a
copy of the same record. Each has one tool built from one template: inputs site_id and wonum (strings, required); outputs
decision (enum), approver_id (string), approver_kind (enum), all required. Actions are named <Target>___<tool>
(pgi.schemagen.generate_dogwood(targets=)), as on AgentCore.

instance(seed) draws from random.Random(sha256("phase3-e1:<seed>")): an unordered pair from names.POOL, a coin flip for which
is AUTH, one of two vocabulary sets, one of three intent paraphrases. Four variants per instance: plain (both tools named
get_approval, byte-identical definitions), echo (the mirror's tool is get_<auth lowercased>_approval), neutral (the mirror's
tool is get_sync_status with no approval fields), untyped_auth (AUTH's outputs are plain strings, the mirror as in plain).

Per instance and variant, `render` writes a loadable scenario folder (pgi.generators.dogwood_inputs, with the t02 folder as its
"domain"): manifests (unprefixed names), the full schema (MaintData + AUTH + MIRROR, session-linked), gold.dw (t01's six
requirements bound to {AUTH}___get_approval), the 19-trace suite, requirements.yaml (workflows, mirror-sufficient set),
admission.catalogue.yaml, intents D0-D4, the eight mutants, instance.json. Enum literals are never built from a naming rule:
the type of each output field is read from the generated schema (the generator merges same-name same-member enums into one
shared entity, e.g. Drupe::decision in plain and echo). Every timestamp is non-negative: M5 and N5 put the approval at @0 and the
close at @4000 instead of placing the approval before time 0.

Committed: this builder, registry.py, intents.py, names.py, schema/ (the MaintData-only schema = prompt part 1), the lock file.
Generated, never committed: instances/.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import re
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
DOMAIN = HERE.parents[1]
ROOT = DOMAIN.parents[1]
sys.path.insert(0, str(HERE))
import intents  # noqa: E402
import registry  # noqa: E402
from names import MAINT_TARGET, POOL  # noqa: E402

from pgi.generators.schema_split import split_schema  # noqa: E402
from pgi.schemagen import generate_dogwood, link_session_id  # noqa: E402

WO_PIN = DOMAIN / "manifests" / "wo.tools.json"
EVENTS = DOMAIN / "schema" / "agentcore.dwschema"
SCHEMA_DIR = HERE / "schema"
BASE_GENERATED, BASE_SCHEMA = SCHEMA_DIR / "maintdata.dogwood.generated.cedarschema", SCHEMA_DIR / "maintdata.dogwood.cedarschema"
INSTANCES = HERE / "instances"
LOCK = HERE / "instances.lock.json"
LOCK_SEEDS = list(range(120)) + list(range(1000, 1020))
VARIANTS = ("plain", "echo", "neutral", "untyped_auth")
VOCABULARIES = ((["GRANTED", "REJECTED", "PENDING"], ["HUMAN", "AGENT", "SYSTEM"]),
                (["ACCEPTED", "REFUSED", "OPEN"], ["PERSON", "AUTOMATION", "SERVICE"]))
CLOSE, APPROVE = f"{MAINT_TARGET}___close_workorder", f"{MAINT_TARGET}___approve_workorder"
WO, OTHER_WO = "1000046", "1000045"
WORKFLOWS = {"direct": ["P1_authority_granted_human", "P5_other_workorder_valid"],
             "reads_mirror": ["P2_authority_then_mirror_positive", "P3_mirror_positive_then_authority"],
             "mirror_negative": ["P4_authority_granted_mirror_negative"]}
MIRROR_SUFFICIENT = ["M1_mirror_positive_only", "M2_authority_rejected_mirror_positive", "M3_authority_pending_mirror_positive",
                     "M4_authority_other_workorder_mirror_this", "M5_authority_expired_mirror_fresh", "M6_authority_request_errored_mirror_positive"]
P_ALL = ["P1_authority_granted_human", "P2_authority_then_mirror_positive", "P3_mirror_positive_then_authority",
         "P4_authority_granted_mirror_negative", "P5_other_workorder_valid"]
MUTANTS = ("mirror_only", "either_source", "both_required", "dropped_outcome", "dropped_approver_kind", "request_not_response",
           "window_24h", "dropped_correlation")


@dataclass(frozen=True)
class Instance:
    seed: int
    auth: str
    mirror: str
    vocab: int        # index into VOCABULARIES
    paraphrase: int   # index into the D0/D1/D2 paraphrases

    @property
    def decisions(self) -> list[str]:
        return VOCABULARIES[self.vocab][0]

    @property
    def kinds(self) -> list[str]:
        return VOCABULARIES[self.vocab][1]


def instance(seed: int) -> Instance:
    rng = random.Random(hashlib.sha256(f"phase3-e1:{seed}".encode()).hexdigest())
    pair = rng.sample(POOL, 2)
    auth = pair[rng.randrange(2)]
    return Instance(seed, auth, next(n for n in pair if n != auth), rng.randrange(2), rng.randrange(3))


def instance_id(seed: int, variant: str) -> str:
    return f"s{seed:04d}-{variant}"


# ---- tool templates
def _inputs(name: str) -> dict:
    return {"properties": {"site_id": {"title": "Site Id", "type": "string"}, "wonum": {"title": "Wonum", "type": "string"}},
            "required": ["site_id", "wonum"], "title": f"{name}Arguments", "type": "object"}


def approval_tool(name: str, decisions: list[str] | None, kinds: list[str] | None) -> dict:
    """The one template behind AUTH and MIRROR: typed outputs when the member lists are given, plain strings otherwise."""
    dec = {"title": "Decision", "type": "string"} | ({"enum": list(decisions)} if decisions else {})
    kind = {"title": "Approver Kind", "type": "string"} | ({"enum": list(kinds)} if kinds else {})
    return {"name": name, "description": "Returns the recorded approval decision for one work order, with who made it and what kind of approver that is.",
            "inputSchema": _inputs(name),
            "outputSchema": {"properties": {"decision": dec, "approver_id": {"title": "Approver Id", "type": "string"}, "approver_kind": kind},
                             "required": ["decision", "approver_id", "approver_kind"], "title": "ApprovalRecord", "type": "object"}}


def sync_tool(name: str) -> dict:
    return {"name": name, "description": "Reports whether this system's copy of one work order is in sync with its source.",
            "inputSchema": _inputs(name),
            "outputSchema": {"properties": {"synced": {"title": "Synced", "type": "boolean"}, "record_id": {"title": "Record Id", "type": "string"}},
                             "required": ["synced", "record_id"], "title": "SyncStatus", "type": "object"}}


def mirror_tool_name(inst: Instance, variant: str) -> str:
    if variant == "neutral":
        return "get_sync_status"
    return f"get_{inst.auth.lower()}_approval" if variant == "echo" else "get_approval"


def tools(inst: Instance, variant: str) -> dict[str, list[dict]]:
    """server -> its tools (unprefixed), for the two per-instance targets."""
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}, got {variant!r}")
    d, k = inst.decisions, inst.kinds
    auth = approval_tool("get_approval", None, None) if variant == "untyped_auth" else approval_tool("get_approval", d, k)
    mirror = sync_tool("get_sync_status") if variant == "neutral" else approval_tool(mirror_tool_name(inst, variant), d, k)
    return {inst.auth: [auth], inst.mirror: [mirror]}


def intent_texts(inst: Instance) -> dict[str, str]:
    return {level: intents.render(level, inst.auth, inst.paraphrase, (inst.decisions, inst.kinds)) for level in intents.LEVELS}


def catalogue(inst: Instance) -> dict:
    """The trusted admission catalogue of an instance (derived from the contract in README.md, never from gold)."""
    return {"protected_action": CLOSE,
            "evidence": {"action": f"{inst.auth}___get_approval", "kind": "response", "max_window": "1h"},
            "correlations": ["site_id", "wonum"],
            "authorizing_values": {"decision": inst.decisions[0], "approver_kind": inst.kinds[0]}}


# ---- schema
def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _dump_json(p: Path, obj) -> None:
    _write(p, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def build_base_schema(dest: Path = SCHEMA_DIR) -> dict[str, str]:
    """The MaintData-only schema (prompt part 1): generated once from the pinned manifest, session-linked. Committed."""
    gen = dest / BASE_GENERATED.name
    _write(gen, generate_dogwood([WO_PIN], targets={WO_PIN: MAINT_TARGET}))
    _write(dest / BASE_SCHEMA.name, link_session_id(gen))
    return {BASE_GENERATED.name: sha(gen), BASE_SCHEMA.name: sha(dest / BASE_SCHEMA.name)}


def generated_schema(inst: Instance, variant: str, workdir: Path) -> tuple[str, dict[str, Path]]:
    """The generated (unlinked) full schema and the manifest files it was generated from (written under workdir)."""
    paths = {}
    for server, ts in tools(inst, variant).items():
        p = workdir / "manifests" / f"{server}.tools.json"
        _dump_json(p, {"tools": ts})
        paths[server] = p
    targets = {WO_PIN: MAINT_TARGET} | {p: server for server, p in paths.items()}
    return generate_dogwood([WO_PIN, *paths.values()], targets=targets), paths


def output_types(schema_text: str, action: str, fields: list[str]) -> dict[str, str | None]:
    """field -> enum entity type name (without namespace) that `<action>Output` declares, or None for a plain String."""
    m = re.search(rf"^  type {re.escape(action)}Output = \{{\n(.*?)\n  \}};", schema_text, re.S | re.M)
    assert m, (action, "no output type in the generated schema")
    out: dict[str, str | None] = {}
    for f in fields:
        fm = re.search(rf"^\s+{re.escape(f)}\??: (?:Drupe::(\w+)|String)", m.group(1), re.M)
        assert fm, (action, f, "not an output field")
        out[f] = fm.group(1)
    return out


def mutation_result_type(schema_text: str) -> str:
    m = re.search(rf"^  type {re.escape(APPROVE)}Output = \{{\n(.*?)\n  \}};", schema_text, re.S | re.M)
    assert m
    fm = re.search(r"typeChoice0\?: Drupe::(\w+)", m.group(1))
    assert fm, "approve_workorder has no success branch"
    return fm.group(1)


def literal(value: str | bool, ty: str | None) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return f'"{value}"' if ty is None else f'Drupe::{ty}::"{value}"'


# ---- traces (event schema: domains/assetopsbench/schema/agentcore.dwschema; gateway wo; principal agent)
_SCOPE = 'scope(principal: Drupe::User::"agent", resource: Drupe::Gateway::"wo")'
_TAIL = 'eventPrincipal: Drupe::User::"agent", eventResource: Drupe::Gateway::"wo", requestId: "{rid}", sessionId: "{sid}")'


def ev_response(ts: int, action: str, wonum: str, output: str, rid: str, sid: str = "s1") -> str:
    return (f"@{ts} {_SCOPE} Drupe::Action::\"{action}\"::response(input: {{ site_id: \"MAIN\", wonum: \"{wonum}\" }}, output: {{ {output} }}, "
            + _TAIL.format(rid=rid, sid=sid))


def ev_request(ts: int, action: str, wonum: str, rid: str, sid: str = "s1") -> str:
    return (f"@{ts} {_SCOPE} request_context(sessionId: \"{sid}\", input: {{ site_id: \"MAIN\", wonum: \"{wonum}\" }}) "
            f"Drupe::Action::\"{action}\"::request(input: {{ site_id: \"MAIN\", wonum: \"{wonum}\" }}, " + _TAIL.format(rid=rid, sid=sid))


def ev_error(ts: int, action: str, wonum: str, rid: str, sid: str = "s1") -> str:
    return f"@{ts} {_SCOPE} Drupe::Action::\"{action}\"::error(input: {{ site_id: \"MAIN\", wonum: \"{wonum}\" }}, " + _TAIL.format(rid=rid, sid=sid)


@dataclass(frozen=True)
class Encoding:
    """Everything needed to render events and predicates for one rendered instance."""

    auth_action: str
    mirror_action: str
    auth_types: dict[str, str | None]
    mirror_types: dict[str, str | None]
    neutral: bool
    mutation_result: str

    def auth_output(self, inst: Instance, decision: str, kind: str, approver: str = "h.lopez") -> str:
        return (f'approver_id: "{approver}", approver_kind: {literal(kind, self.auth_types["approver_kind"])}, '
                f'decision: {literal(decision, self.auth_types["decision"])}')

    def mirror_output(self, inst: Instance, positive: bool) -> str:
        if self.neutral:
            return f'record_id: "r1", synced: {literal(positive, None)}'
        d, k = (inst.decisions[0], inst.kinds[0]) if positive else (inst.decisions[1], inst.kinds[1])
        return (f'approver_id: "h.lopez", approver_kind: {literal(k, self.mirror_types["approver_kind"])}, '
                f'decision: {literal(d, self.mirror_types["decision"])}')

    def auth_bindings(self, inst: Instance) -> list[str]:
        return [f'output.decision: {literal(inst.decisions[0], self.auth_types["decision"])}',
                f'output.approver_kind: {literal(inst.kinds[0], self.auth_types["approver_kind"])}']

    def mirror_bindings(self, inst: Instance) -> list[str]:
        if self.neutral:
            return ["output.synced: true"]
        return [f'output.decision: {literal(inst.decisions[0], self.mirror_types["decision"])}',
                f'output.approver_kind: {literal(inst.kinds[0], self.mirror_types["approver_kind"])}']


def traces(inst: Instance, enc: Encoding) -> list[dict]:
    """The 19 traces: id, contract, lines, note. Close of 1000046@MAIN at @600 in session s1 unless noted; no negative timestamp."""
    d, k = inst.decisions, inst.kinds
    A = lambda ts, decision=d[0], kind=k[0], wonum=WO, sid="s1", approver="h.lopez": ev_response(ts, enc.auth_action, wonum, enc.auth_output(inst, decision, kind, approver), "a1", sid)
    M = lambda ts, positive=True, wonum=WO: ev_response(ts, enc.mirror_action, wonum, enc.mirror_output(inst, positive), "g1")
    close = lambda ts=600, wonum=WO, sid="s1", rid="c1": ev_request(ts, CLOSE, wonum, rid, sid)
    native = ev_response(100, APPROVE, WO, f"result: {{ typeChoice0: Drupe::{enc.mutation_result}::\"m1\" }}", "p1")
    mp = "mirror positive" + ("" if not enc.neutral else " (synced: true)")
    return [
        {"id": "P1_authority_granted_human", "contract": "allow", "lines": [A(100), close()],
         "note": f"{inst.auth} response {d[0]}/{k[0]} for 1000046@MAIN at @100, same session, 500 s before the close"},
        {"id": "P2_authority_then_mirror_positive", "contract": "allow", "lines": [A(100), M(200), close()],
         "note": f"{inst.auth} {d[0]}/{k[0]} at @100, then {inst.mirror} {mp} at @200: the mirror record is extra history the contract ignores"},
        {"id": "P3_mirror_positive_then_authority", "contract": "allow", "lines": [M(100), A(200), close()],
         "note": f"{inst.mirror} {mp} at @100, then {inst.auth} {d[0]}/{k[0]} at @200"},
        {"id": "P4_authority_granted_mirror_negative", "contract": "allow", "lines": [A(100), M(200, positive=False), close()],
         "note": f"{inst.auth} {d[0]}/{k[0]} at @100, {inst.mirror} negative at @200: the mirror's copy does not override the system of record"},
        {"id": "P5_other_workorder_valid", "contract": "allow", "lines": [A(100, wonum=OTHER_WO), close(wonum=OTHER_WO)],
         "note": f"{inst.auth} {d[0]}/{k[0]} for the OTHER work order 1000045@MAIN at @100; close of 1000045@MAIN. Measures deficit (a policy that hard-codes 1000046)"},
        {"id": "M1_mirror_positive_only", "contract": "deny", "lines": [M(100), close()],
         "note": f"only {inst.mirror} {mp} at @100; no {inst.auth} response. Requirement 6 (provenance): the mirror is not the system of record"},
        {"id": "M2_authority_rejected_mirror_positive", "contract": "deny", "lines": [A(100, decision=d[1]), M(200), close()],
         "note": f"{inst.auth} {d[1]}/{k[0]} at @100, {inst.mirror} {mp} at @200. Requirement 2 (outcome); the mirror cannot rescue it"},
        {"id": "M3_authority_pending_mirror_positive", "contract": "deny", "lines": [A(100, decision=d[2]), M(200), close()],
         "note": f"{inst.auth} {d[2]}/{k[0]} at @100, {inst.mirror} {mp} at @200. Requirement 2"},
        {"id": "M4_authority_other_workorder_mirror_this", "contract": "deny", "lines": [A(100, wonum=OTHER_WO), M(200), close()],
         "note": f"{inst.auth} {d[0]}/{k[0]} for 1000045 at @100, {inst.mirror} {mp} for 1000046 at @200. Requirement 4 (correlation)"},
        {"id": "M5_authority_expired_mirror_fresh", "contract": "deny", "lines": [A(0), M(3900), close(ts=4000)],
         "note": f"{inst.auth} {d[0]}/{k[0]} at @0, {inst.mirror} {mp} at @3900, close at @4000 (4000 s after the approval; window 3600 s). Requirement 3 (time)"},
        {"id": "M6_authority_request_errored_mirror_positive", "contract": "deny",
         "lines": [ev_request(100, enc.auth_action, WO, "a1"), ev_error(101, enc.auth_action, WO, "a1"), M(200), close()],
         "note": f"the agent asked {inst.auth} (request at @100, permitted by lookup-approval) and the call errored at @101; {inst.mirror} {mp} at @200. Requirement 6 (completed response, not an attempt)"},
        {"id": "N1_rejected", "contract": "deny", "lines": [A(100, decision=d[1]), close()], "note": f"the decision of record is {d[1]}"},
        {"id": "N2_pending", "contract": "deny", "lines": [A(100, decision=d[2]), close()], "note": f"the decision of record is still {d[2]}"},
        {"id": "N3_approver_not_human", "contract": "deny", "lines": [A(100, kind=k[1], approver="agent"), close()],
         "note": f"{d[0]} but recorded as made by the agent ({k[1]}). Requirement 1 (identity)"},
        {"id": "N4_wrong_workorder", "contract": "deny", "lines": [A(100, wonum=OTHER_WO), close()],
         "note": f"{d[0]}/{k[0]} but for the other MAIN work order (1000045). Requirement 4"},
        {"id": "N5_expired", "contract": "deny", "lines": [A(0), close(ts=4000)],
         "note": f"{d[0]}/{k[0]} at @0, close at @4000 (window 1h = 3600 s, inclusive). Requirement 3"},
        {"id": "N6_other_session", "contract": "deny", "lines": [A(100), close(sid="s2")],
         "note": "the evidence of P1, but the close is in session s2. Requirement 5 (session pin)"},
        {"id": "N7_no_history", "contract": "deny", "lines": [close()], "note": "nothing before the close"},
        {"id": "N8_native_approve_success_only", "contract": "deny", "lines": [native, close()],
         "note": f"a successful native {APPROVE} response by the agent at @100; no {inst.auth} record. Requirement 6 (source) and 1"},
    ]


# ---- policies
def _permit(pid: str, action_pred: str, kind: str, bindings: list[str], window: str = "1h") -> str:
    body = ",\n".join(["    eventResource: resource", "    input.wonum: context.input.wonum", "    input.site_id: context.input.site_id", *("    " + b for b in bindings)])
    return (f'@id("{pid}")\npermit (principal, action == Drupe::Action::"{CLOSE}", resource)\nwhen {{ context.input.site_id == "MAIN" }}\n'
            f'when temporal {{\n  formerly within {window} Drupe::Action::"{action_pred}"::{kind}{{\n{body}\n  }}\n}};\n')


def _lookup(auth_action: str) -> str:
    return f'@id("lookup-approval")\npermit (principal, action == Drupe::Action::"{auth_action}", resource);\n'


def gold(inst: Instance, enc: Encoding) -> str:
    head = (f"// t02_designated_source gold: t01's six requirements bound to {enc.auth_action} (the designated system of record).\n"
            "// Event schema: domains/assetopsbench/schema/agentcore.dwschema. Contract: README.md. Generated by build_instances.py.\n")
    return head + _permit("close-after-designated-approval", enc.auth_action, "response", enc.auth_bindings(inst)) + "\n" + _lookup(enc.auth_action)


def mutants(inst: Instance, enc: Encoding) -> dict[str, tuple[str, list[str]]]:
    """name -> (policy text, expected kill set = traces where it differs from gold). Each is gold with one change."""
    a, m = enc.auth_action, enc.mirror_action
    ab, mb = enc.auth_bindings(inst), enc.mirror_bindings(inst)
    both_body = ",\n".join(["    eventResource: resource", "    input.wonum: context.input.wonum", "    input.site_id: context.input.site_id"])
    both = (f'@id("close-after-both")\npermit (principal, action == Drupe::Action::"{CLOSE}", resource)\nwhen {{ context.input.site_id == "MAIN" }}\n'
            f'when temporal {{\n  formerly within 1h Drupe::Action::"{a}"::response{{\n{both_body},\n' + ",\n".join("    " + b for b in ab) + "\n  }\n"
            f'  && formerly within 1h Drupe::Action::"{m}"::response{{\n{both_body},\n' + ",\n".join("    " + b for b in mb) + "\n  }\n};\n")
    lk = _lookup(a)
    return {
        # P2 and P3 carry the mirror positive, so the mirror-bound predicate allows them like gold: only P1, P4, P5 are newly denied
        "mirror_only": (_permit("close-after-designated-approval", m, "response", mb) + "\n" + lk,
                        ["P1_authority_granted_human", "P4_authority_granted_mirror_negative", "P5_other_workorder_valid"] + MIRROR_SUFFICIENT),
        "either_source": (_permit("close-after-designated-approval", a, "response", ab) + "\n" + _permit("close-after-mirror", m, "response", mb) + "\n" + lk, MIRROR_SUFFICIENT),
        "both_required": (both + "\n" + lk, ["P1_authority_granted_human", "P4_authority_granted_mirror_negative", "P5_other_workorder_valid"]),
        "dropped_outcome": (_permit("close-after-designated-approval", a, "response", ab[1:]) + "\n" + lk,
                            ["M2_authority_rejected_mirror_positive", "M3_authority_pending_mirror_positive", "N1_rejected", "N2_pending"]),
        "dropped_approver_kind": (_permit("close-after-designated-approval", a, "response", ab[:1]) + "\n" + lk, ["N3_approver_not_human"]),
        "request_not_response": (_permit("close-after-designated-approval", a, "request", []) + "\n" + lk, P_ALL + ["M6_authority_request_errored_mirror_positive"]),
        "window_24h": (_permit("close-after-designated-approval", a, "response", ab, window="24h") + "\n" + lk, ["M5_authority_expired_mirror_fresh", "N5_expired"]),
        "dropped_correlation": (_permit("close-after-designated-approval", a, "response", ab).replace("    input.wonum: context.input.wonum,\n", "") + "\n" + lk,
                                ["M4_authority_other_workorder_mirror_this", "N4_wrong_workorder"]),
    }


def requirements(inst: Instance, enc: Encoding, variant: str) -> dict:
    stated = [] if variant == "neutral" else inst.decisions + inst.kinds
    return {
        "base": "P1_authority_granted_human",
        "requirements": {
            "outcome": {"requirement": 2, "witnesses": ["N1_rejected", "N2_pending"]},
            "approver": {"requirement": 1, "witnesses": ["N3_approver_not_human"]},
            "binding": {"requirement": 4, "witnesses": ["N4_wrong_workorder"]},
            "window": {"requirement": 3, "witnesses": ["N5_expired"]},
            "session": {"requirement": 5, "witnesses": ["N6_other_session"]},
            "provenance_kind": {"requirement": 6, "witnesses": ["M6_authority_request_errored_mirror_positive"]},
            "provenance_source": {"requirement": 6, "witnesses": MIRROR_SUFFICIENT + ["N8_native_approve_success_only"]},
        },
        "security": {"over_permissive_if_allows": MIRROR_SUFFICIENT + ["N3_approver_not_human", "N8_native_approve_success_only"],
                     "over_strict_if_denies": P_ALL},
        "evidence_sources": {"authority": "P1_authority_granted_human", "mirror": "M1_mirror_positive_only",
                             "native_approve": "N8_native_approve_success_only", "no_evidence": "N7_no_history"},
        "prerequisite_call": {"trace": "M6_authority_request_errored_mirror_positive", "decision_index": 0},
        "vendor_only_traces": MIRROR_SUFFICIENT,          # the mirror-sufficient set (primary outcome: allows any), under the loader's key
        "mirror_sufficient_traces": MIRROR_SUFFICIENT,
        "evidence_vocabulary": {"authority_action": enc.auth_action, "vendor_actions": [enc.mirror_action],
                                "contract_values": inst.decisions + inst.kinds, "vendor_stated_values": stated,
                                "approver_kind_fields": ["output.approver_kind"]},
        "workflows": WORKFLOWS,
    }


def _scenario_yaml(inst: Instance, variant: str, iid: str) -> str:
    man = {MAINT_TARGET: "../../manifests/wo.tools.json", inst.auth: f"instances/{iid}/manifests/{inst.auth}.tools.json",
           inst.mirror: f"instances/{iid}/manifests/{inst.mirror}.tools.json"}
    meta = {"track": "dogwood", "schema": f"instances/{iid}/schema/t02.dogwood.cedarschema", "event_schema": "../../schema/agentcore.dwschema",
            "prompt_schema_base": f"schema/{BASE_SCHEMA.name}", "traces": "traces.yaml", "gold": "gold.dw",
            "servers": [MAINT_TARGET, inst.auth, inst.mirror], "manifests": man, "intent": "intents/D0.md",
            "intents": {level: f"intents/{level}.md" for level in intents.LEVELS}, "requirements": "requirements.yaml",
            "catalogue": "admission.catalogue.yaml"}
    head = (f"# t02_designated_source instance {iid} (seed {inst.seed}, variant {variant}); generated by build_instances.py, not committed.\n"
            "# Paths relative to the t02 scenario folder (this instance's 'domain' for pgi.generators.dogwood_inputs); the rest to this folder.\n"
            "# D4 = --intent D4 with the generator's contract_block set (the intent file is D0's text).\n")
    return head + yaml.safe_dump(meta, sort_keys=False, width=200)


def _tree_hashes(dest: Path) -> dict[str, str]:
    return {str(p.relative_to(dest)): sha(p) for p in sorted(dest.rglob("*")) if p.is_file()}


def render(inst: Instance, variant: str, dest: Path) -> dict:
    """Write one instance folder (removing any previous one) and return its record (instance.json)."""
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    iid = instance_id(inst.seed, variant)
    gen_text, _ = generated_schema(inst, variant, dest)
    gen = dest / "schema" / "t02.dogwood.generated.cedarschema"
    _write(gen, gen_text)
    full = link_session_id(gen)
    _write(dest / "schema" / "t02.dogwood.cedarschema", full)
    if not BASE_SCHEMA.is_file():
        raise FileNotFoundError(f"{BASE_SCHEMA} missing: run build_instances.py --base first")
    split_schema(full, BASE_SCHEMA.read_text())     # every MaintData declaration unchanged; raises otherwise
    auth_action, mirror_action = f"{inst.auth}___get_approval", f"{inst.mirror}___{mirror_tool_name(inst, variant)}"
    enc = Encoding(auth_action, mirror_action, output_types(gen_text, auth_action, ["decision", "approver_kind"]),
                   {} if variant == "neutral" else output_types(gen_text, mirror_action, ["decision", "approver_kind"]),
                   variant == "neutral", mutation_result_type(gen_text))
    _write(dest / "gold.dw", gold(inst, enc))
    entries = []
    for t in traces(inst, enc):
        _write(dest / "traces" / f"{t['id']}.log", "\n".join(t["lines"]) + "\n")
        entries.append({"id": t["id"], "file": f"traces/{t['id']}.log", "contract": t["contract"], "note": t["note"]})
    _write(dest / "traces.yaml", f"# t02_designated_source {iid}: expected decision of the FINAL {CLOSE} request; session s1, gateway wo; "
                                  "event schema agentcore.dwschema (sessionId pin). Generated by build_instances.py.\n"
           + yaml.safe_dump({"traces": entries}, sort_keys=False, width=200))
    _write(dest / "requirements.yaml", f"# t02_designated_source {iid} scoring metadata (never shown to a generator); generated by build_instances.py.\n"
           + yaml.safe_dump(requirements(inst, enc, variant), sort_keys=False, width=200))
    _write(dest / "admission.catalogue.yaml", f"# t02_designated_source {iid} trusted admission catalogue, derived from README.md's contract; generated.\n"
           + yaml.safe_dump(catalogue(inst), sort_keys=False))
    for level, text in intent_texts(inst).items():
        _write(dest / "intents" / f"{level}.md", text)
    expected = {}
    for name, (text, kills) in mutants(inst, enc).items():
        _write(dest / "mutants" / f"{name}.dw", f"// mutant {name} ({iid}): gold with one change; generated by build_instances.py\n" + text)
        expected[name] = sorted(kills)
    _write(dest / "scenario.yaml", _scenario_yaml(inst, variant, iid))
    record = {"id": iid, "variant": variant, "draw": asdict(inst), "vocabulary": {"decisions": inst.decisions, "kinds": inst.kinds},
              "actions": {"close": CLOSE, "authority": auth_action, "mirror": mirror_action},
              "enum_types": {"authority": enc.auth_types, "mirror": enc.mirror_types},
              "shared_enum_types": sorted(set(filter(None, enc.auth_types.values())) & set(filter(None, enc.mirror_types.values()))),
              "mutants_expected_kills": expected, "workflows": WORKFLOWS, "mirror_sufficient": MIRROR_SUFFICIENT,
              "registry_sha256": registry.REGISTRY.sha256(), "intents_sha256": sha(HERE / "intents.py"), "names_sha256": sha(HERE / "names.py"),
              "base_schema_sha256": sha(BASE_SCHEMA), "event_schema_sha256": sha(EVENTS), "wo_pin_sha256": sha(WO_PIN)}
    _dump_json(dest / "instance.json", record)
    record["sha256"] = _tree_hashes(dest)
    return record


def lock_entry(record: dict) -> dict:
    files = {k: v for k, v in record["sha256"].items() if not k.startswith("traces/")}
    trace_hashes = "".join(v for k, v in sorted(record["sha256"].items()) if k.startswith("traces/"))
    tree = hashlib.sha256("".join(f"{k} {v}\n" for k, v in sorted(record["sha256"].items())).encode()).hexdigest()
    return {"seed": record["draw"]["seed"], "variant": record["variant"], "auth": record["draw"]["auth"], "mirror": record["draw"]["mirror"],
            "vocab": record["draw"]["vocab"], "paraphrase": record["draw"]["paraphrase"], "tree_sha256": tree,
            "traces_sha256": hashlib.sha256(trace_hashes.encode()).hexdigest(), "files": files}


def build_lock(seeds: list[int], variants: tuple[str, ...], workdir: Path) -> dict:
    from importlib.metadata import version

    entries = {}
    for seed in seeds:
        inst = instance(seed)
        for variant in variants:
            iid = instance_id(seed, variant)
            entries[iid] = lock_entry(render(inst, variant, workdir / iid))
    return {"builder": "domains/assetopsbench/scenarios/t02_designated_source/build_instances.py", "pydogwood": version("pydogwood"),
            "seeds": seeds, "variants": list(variants), "registry_sha256": registry.REGISTRY.sha256(), "intents_sha256": sha(HERE / "intents.py"),
            "names_sha256": sha(HERE / "names.py"), "base_schema_sha256": sha(BASE_SCHEMA), "wo_pin_sha256": sha(WO_PIN), "instances": entries}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base", action="store_true", help="write schema/ (the MaintData-only schema, prompt part 1)")
    p.add_argument("--render", type=int, nargs="*", help="seeds to render under instances/")
    p.add_argument("--variants", nargs="*", default=list(VARIANTS), choices=VARIANTS)
    p.add_argument("--lock", action="store_true", help="render the lock seeds into a temp folder and write instances.lock.json")
    p.add_argument("--check", action="store_true", help="rebuild the lock's instances into a temp folder and compare with instances.lock.json")
    args = p.parse_args()
    if args.base:
        for name, h in build_base_schema().items():
            print(h, name)
    if args.render is not None:
        for seed in args.render:
            inst = instance(seed)
            for variant in args.variants:
                rec = render(inst, variant, INSTANCES / instance_id(seed, variant))
                print(rec["id"], inst.auth, inst.mirror, "vocab", inst.vocab, "paraphrase", inst.paraphrase, "shared", rec["shared_enum_types"])
    if args.lock or args.check:
        with tempfile.TemporaryDirectory() as tmp:
            lock = build_lock(LOCK_SEEDS, VARIANTS, Path(tmp))
        if args.lock:
            _dump_json(LOCK, lock)
            print(f"wrote {LOCK}: {len(lock['instances'])} instances")
        if args.check:
            old = json.loads(LOCK.read_text())
            diff = [k for k in set(old["instances"]) | set(lock["instances"]) if old["instances"].get(k) != lock["instances"].get(k)]
            meta = [k for k in ("registry_sha256", "intents_sha256", "names_sha256", "base_schema_sha256", "wo_pin_sha256") if old.get(k) != lock.get(k)]
            print("lock check:", "OK" if not diff and not meta else f"DIFFERS: instances {sorted(diff)[:10]} ({len(diff)}), meta {meta}")
            if diff or meta:
                sys.exit(1)


if __name__ == "__main__":
    main()
