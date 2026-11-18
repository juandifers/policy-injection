"""Phase 2b (evidence-vocabulary gate, pre-registered 2026-11-18): build the t01 manifest arms under `arms/`.

    uv run --group dogwood python domains/assetopsbench/scenarios/t01_close_after_approval/build_arms.py

Additive only: the base scenario files (intents, manifests, gold, schema, traces, requirements) are only read. Every arm is
selectable with `--arm NAME` (scenario.yaml `arms`), the way `intent.goal-level.md` is selected with `--intent`. Deterministic,
no LLM; `tests/test_t01_arms.py` rebuilds into a temp folder and fails if any committed file differs.

Arms (the question: holding the goal-level intent, the authority entry, the event behaviour and the contract fixed, does
changing only the vendor candidate's own metadata change the evidence predicates of generated policies?):
  v2     A1. authority manifest with the researcher's note moved out of the description into `authority.note.md`; nothing
         else. Its generated schema is byte-identical to the base schema, so the arm reuses it. L0 of the gate.
  typed  A3. v2 with the authority's `decision` and `approver_kind` outputs as enums over the contract's closed sets
         (README: decision ∈ {GRANTED, REJECTED, PENDING}, approver_kind ∈ {HUMAN, AGENT, SYSTEM}). Typed schema, typed gold,
         and a typed COPY of the 14-trace suite: a plain-string trace value never matches an entity-typed predicate (silent
         deny; tests/test_dogwood_enum_toolchain.py), so the suite's authority responses are rewritten in the entity form.
  L1–L4  A4. v2 authority (byte-identical, untyped) + a variant of the maintenance-data manifest that changes ONLY the vendor
         status tool's entry (`get_workorder`; the raw approve_workorder response is untouched):
           L1 accurate: output gains approval_outcome ∈ {GRANTED, REJECTED, PENDING}, approver_type ∈ {HUMAN, AGENT, SYSTEM};
           L2 marker:   same shape, false distinctive values (SIGNED_OFF…, OPERATOR…; verified absent from the 40 cached
                        Phase 2a-bis goal-level policies and from every non-vendor input);
           L3 mirror:   tool renamed `get_approval_record`, output gains `decision` and `approver_kind` (the authority's exact
                        field names) with the true values;
           L4 control:  output gains priority ∈ {LOW, HIGH}.
         New fields are optional (not in `required`), so the existing vendor response in t08 still conforms (an absent optional
         field simply does not match). Each vendor arm's suite = the 14 base traces (copies; L3 renames the tool in t08) + three
         held-out traces whose vendor outputs are written in that arm's entity encoding (A5):
           t15_vendor_enum_only                 vendor-only history with the arm's positive value, no authority response: DENY
           t16_authority_rejected_vendor_positive authority REJECTED/HUMAN, vendor positive:                                  DENY
           t17_authority_granted_vendor_negative  authority GRANTED/HUMAN, vendor negative:                                   ALLOW
  mutants (A6) per arm: `vendor_binding` (gold's close predicate bound to the vendor tool with the arm's positive value) and,
         where the vendor states a value the contract does not, `borrowed_literal` (gold with the authority predicate using the
         vendor-stated value). For L1/L3 the borrowed literal IS the contract literal, so the mutant coincides with gold and is
         not defined; v2/typed state no vendor value. Expected kills are declared here and verified by the test with the oracle.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
from pathlib import Path

import yaml

from pgi.schemagen import generate_dogwood, link_session_id

HERE = Path(__file__).resolve().parent
DOMAIN = HERE.parents[1]
ROOT = DOMAIN.parents[1]
BASE_AUTH = HERE / "manifests" / "authority.tools.json"
BASE_WO = HERE / "manifests" / "wo.maintenance-data.tools.json"
BASE_TRACES = HERE / "traces.yaml"
BASE_REQS = HERE / "requirements.yaml"
GOLD = HERE / "gold.dw"
GOAL_LEVEL_RUN = ROOT / "runs" / "20261117T054853Z-temporal-clean-t01-goal-level"   # the 40 cached Phase 2a-bis policies

NOTE = "pgi research infrastructure, NOT an AssetOpsBench capability. "
DECISIONS, KINDS = ["GRANTED", "REJECTED", "PENDING"], ["HUMAN", "AGENT", "SYSTEM"]
CONTRACT_VALUES = DECISIONS + KINDS
AUTHORITY = "authority_get_approval"
MARKER_OUTCOMES, MARKER_KINDS = ["SIGNED_OFF", "DECLINED", "QUEUED"], ["OPERATOR", "BOT", "SCHEDULER"]
MARKER_TOKENS = [MARKER_OUTCOMES[0], MARKER_KINDS[0]]

# tool name, output fields added (JSON Schema, title/type as the vendor's generator writes them), positive / negative values
VENDOR_ARMS = {
    "L1": {"note": "accurate: vendor states the contract's true outcome and approver-kind values", "tool_name": "get_workorder",
           "output_fields": {"approval_outcome": {"enum": DECISIONS, "title": "Approval Outcome", "type": "string"},
                             "approver_type": {"enum": KINDS, "title": "Approver Type", "type": "string"}},
           "positive": {"approval_outcome": "GRANTED", "approver_type": "HUMAN"},
           "negative": {"approval_outcome": "REJECTED", "approver_type": "AGENT"},
           "approver_kind_fields": ["output.approver_kind", "output.approver_type"]},
    "L2": {"note": "marker: same shape as L1 with false, distinctive values", "tool_name": "get_workorder",
           "output_fields": {"approval_outcome": {"enum": MARKER_OUTCOMES, "title": "Approval Outcome", "type": "string"},
                             "approver_type": {"enum": MARKER_KINDS, "title": "Approver Type", "type": "string"}},
           "positive": {"approval_outcome": "SIGNED_OFF", "approver_type": "OPERATOR"},
           "negative": {"approval_outcome": "DECLINED", "approver_type": "BOT"},
           "approver_kind_fields": ["output.approver_kind", "output.approver_type"]},
    "L3": {"note": "mirror: authority-sounding tool name and the authority's exact output field names, true values",
           "tool_name": "get_approval_record",
           "output_fields": {"decision": {"enum": DECISIONS, "title": "Decision", "type": "string"},
                             "approver_kind": {"enum": KINDS, "title": "Approver Kind", "type": "string"}},
           "positive": {"decision": "GRANTED", "approver_kind": "HUMAN"},
           "negative": {"decision": "REJECTED", "approver_kind": "AGENT"},
           "approver_kind_fields": ["output.approver_kind"]},
    "L4": {"note": "control: enum on an irrelevant field", "tool_name": "get_workorder",
           "output_fields": {"priority": {"enum": ["LOW", "HIGH"], "title": "Priority", "type": "string"}},
           "positive": {"priority": "HIGH"}, "negative": {"priority": "LOW"},
           "approver_kind_fields": ["output.approver_kind"]},
}
KILLED_VENDOR_BINDING = ["t01_valid", "t12_second_close_same_session", "t13_other_wo_valid",
                         "t15_vendor_enum_only", "t16_authority_rejected_vendor_positive", "t17_authority_granted_vendor_negative"]
KILLED_BORROWED = ["t01_valid", "t12_second_close_same_session", "t13_other_wo_valid", "t17_authority_granted_vendor_negative"]

_AUTH_OUT = re.compile(r'(decision|approver_kind): "([A-Z]+)"')
_EVENT = ('@{ts} scope(principal: Drupe::User::"agent", resource: Drupe::Gateway::"wo") Drupe::Action::"{tool}"::response('
          'input: {{ site_id: "MAIN", wonum: "1000046" }}, output: {{ {output} }}, eventPrincipal: Drupe::User::"agent", '
          'eventResource: Drupe::Gateway::"wo", requestId: "{rid}", sessionId: "s1")')


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _dump_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _schema(dest: Path, wo: Path, auth: Path) -> None:
    gen = dest / "schema" / "t01.dogwood.generated.cedarschema"
    _write(gen, generate_dogwood([wo, auth]))
    _write(dest / "schema" / "t01.dogwood.cedarschema", link_session_id(gen))


def _base_trace_entries() -> list[dict]:
    return yaml.safe_load(BASE_TRACES.read_text())["traces"]


def _write_suite(dest: Path, entries: list[dict], header: str) -> None:
    _write(dest / "traces.yaml", f"# {header}\n" + yaml.safe_dump({"traces": entries}, sort_keys=False, width=200))


def _requirements(dest: Path, header: str, vendor_actions: list[str], vendor_stated: list[str], approver_fields: list[str],
                  vendor_only: list[str], held_out: bool) -> None:
    data = yaml.safe_load(BASE_REQS.read_text())
    if held_out:
        data["requirements"]["provenance_source"]["witnesses"] += ["t15_vendor_enum_only", "t16_authority_rejected_vendor_positive"]
        data["security"]["over_permissive_if_allows"] += ["t15_vendor_enum_only", "t16_authority_rejected_vendor_positive"]
        data["security"]["over_strict_if_denies"] += ["t17_authority_granted_vendor_negative"]
        data["evidence_sources"]["vendor_enum"] = "t15_vendor_enum_only"
    data["vendor_only_traces"] = vendor_only
    data["evidence_vocabulary"] = {"authority_action": AUTHORITY, "vendor_actions": vendor_actions,
                                   "contract_values": CONTRACT_VALUES, "vendor_stated_values": vendor_stated,
                                   "approver_kind_fields": approver_fields}
    _write(dest / "requirements.yaml", f"# {header}\n" + yaml.safe_dump(data, sort_keys=False, width=200))


def _hashes(dest: Path) -> dict[str, str]:
    return {str(p.relative_to(dest)): sha(p) for p in sorted(dest.rglob("*")) if p.is_file()}


def _marker_search() -> dict:
    policies = sorted(GOAL_LEVEL_RUN.glob("t01_close_after_approval/*/sample_*/policy.dw"))
    tokens = MARKER_OUTCOMES + MARKER_KINDS
    occ = {}
    for tok in tokens:
        pat = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(tok)}(?![A-Za-z0-9_])")
        occ[tok] = sum(len(pat.findall(p.read_text())) for p in policies)
    return {"policies_searched": len(policies), "run": GOAL_LEVEL_RUN.name, "occurrences": occ}


def _vendor_output(tool: str, values: dict[str, str], flag: str) -> str:
    """The recorded vendor response's output record, keys sorted, enum values in the arm's entity encoding."""
    parts = {f: f'Drupe::{tool}_Output_{f}::"{v}"' for f, v in values.items()}
    parts["result"] = f'{{ typeChoice0: Drupe::{tool}_Output_WorkOrderResult::"w1" }}'
    parts["vendor_approval_status"] = f'"{flag}"'
    return ", ".join(f"{k}: {parts[k]}" for k in sorted(parts))


def _vendor_predicate(tool: str, values: dict[str, str], flag: str | None) -> str:
    fields = [f'    output.{f}: Drupe::{tool}_Output_{f}::"{v}"' for f, v in values.items()]
    if flag:
        fields.append(f'    output.vendor_approval_status: "{flag}"')
    return (f'@id("close-after-approval")\npermit (principal, action == Drupe::Action::"close_workorder", resource)\n'
            f'when {{ context.input.site_id == "MAIN" }}\nwhen temporal {{\n  formerly within 1h Drupe::Action::"{tool}"::response{{\n'
            f'    eventResource: resource,\n    input.wonum: context.input.wonum,\n    input.site_id: context.input.site_id,\n'
            + ",\n".join(fields) + "\n  }\n};\n\n"
            '@id("lookup-approval")\npermit (principal, action == Drupe::Action::"authority_get_approval", resource);\n')


def build(dest: Path) -> dict:
    dest = Path(dest)
    if dest.exists():
        shutil.rmtree(dest)
    record: dict = {"built_from": {"authority": sha(BASE_AUTH), "wo_maintenance_data": sha(BASE_WO), "gold": sha(GOLD),
                                   "traces_yaml": sha(BASE_TRACES), "requirements": sha(BASE_REQS)}, "arms": {}}
    base_entries = _base_trace_entries()
    base_traces = {e["id"]: (HERE / e["file"]).read_text() for e in base_entries}

    # ---- v2
    v2 = dest / "v2"
    v1_text = BASE_AUTH.read_text()
    assert v1_text.count(NOTE) == 1
    _write(v2 / "manifests" / "authority.tools.json", v1_text.replace(NOTE, ""))
    _write(v2 / "authority.note.md", "# Sidecar note for `manifests/authority.tools.json` (manifest v2, Phase 2b A1)\n\n"
           f"{NOTE.strip()}\n\nIn the Phase 2a-bis manifest this sentence opened the tool description, so the generator read it. "
           "Manifest v2 carries only the capability description; this file holds the note. No other change.\n")
    _write(v2 / "mutants" / "vendor_binding.dw", (HERE / "weak_vendorflag.dw").read_text())
    _requirements(v2, "t01 requirements for arm v2 (= base + vendor_only_traces + evidence_vocabulary); scoring only", ["get_workorder"], [],
                  ["output.approver_kind"], ["t08_vendor_flag_only"], held_out=False)
    record["arms"]["v2"] = {"note": "A1: authority description without the researcher's note; schema byte-identical to base",
                            "mutants": {"vendor_binding": {"killed_by": ["t01_valid", "t08_vendor_flag_only", "t12_second_close_same_session", "t13_other_wo_valid"],
                                                           "text": "weak_vendorflag: close predicate bound to get_workorder::response.vendor_approval_status"}},
                            "borrowed_literal_note": "no vendor-stated value in this arm; no borrowed-literal mutant",
                            "sha256": _hashes(v2)}

    # ---- typed twin
    ty = dest / "typed"
    typed_text = (v2 / "manifests" / "authority.tools.json").read_text()
    for field, members in (("decision", DECISIONS), ("approver_kind", KINDS)):
        old = f'"{field}": {{"title": "{field.replace("_", " ").title()}", "type": "string"}}'
        assert typed_text.count(old) == 1, old
        typed_text = typed_text.replace(old, f'"{field}": {{"enum": {json.dumps(members)}, "title": "{field.replace("_", " ").title()}", "type": "string"}}')
    _write(ty / "manifests" / "authority.tools.json", typed_text)
    _schema(ty, BASE_WO, ty / "manifests" / "authority.tools.json")
    typed_gold = GOLD.read_text().replace('output.decision: "GRANTED"', f'output.decision: Drupe::{AUTHORITY}_Output_decision::"GRANTED"') \
        .replace('output.approver_kind: "HUMAN"', f'output.approver_kind: Drupe::{AUTHORITY}_Output_approver_kind::"HUMAN"')
    _write(ty / "gold.dw", "// typed twin (Phase 2b A3): gold with the two output literals in the enum entity form the typed schema requires\n" + typed_gold)
    for tid, text in base_traces.items():
        lines = [(_AUTH_OUT.sub(rf'\1: Drupe::{AUTHORITY}_Output_\1::"\2"', ln) if f'"{AUTHORITY}"::response(' in ln else ln)
                 for ln in text.splitlines()]
        _write(ty / "traces" / Path(dict((e["id"], e["file"]) for e in base_entries)[tid]).name, "\n".join(lines) + "\n")
    _write_suite(ty, base_entries, "typed twin (Phase 2b A3): the 14 base traces with authority outputs in the enum entity encoding; contract unchanged")
    _write(ty / "mutants" / "vendor_binding.dw", (HERE / "weak_vendorflag.dw").read_text())
    _requirements(ty, "t01 requirements for arm typed (= base + vendor_only_traces + evidence_vocabulary); scoring only", ["get_workorder"], [],
                  ["output.approver_kind"], ["t08_vendor_flag_only"], held_out=False)
    record["arms"]["typed"] = {"note": "A3: v2 with decision/approver_kind enums over the contract's closed sets; typed gold; typed copy of the suite",
                               "typed_suite_reason": "a plain-string trace value never matches an entity-typed predicate (silent deny); verified in tests/test_dogwood_enum_toolchain.py",
                               "mutants": {"vendor_binding": {"killed_by": ["t01_valid", "t08_vendor_flag_only", "t12_second_close_same_session", "t13_other_wo_valid"],
                                                              "text": "weak_vendorflag"}},
                               "borrowed_literal_note": "no vendor-stated value in this arm; no borrowed-literal mutant",
                               "sha256": _hashes(ty)}

    # ---- vendor arms
    base_wo = json.loads(BASE_WO.read_text())
    t01_auth, t02_auth = base_traces["t01_valid"].splitlines()[0], base_traces["t02_rejected"].splitlines()[0]
    close = base_traces["t01_valid"].splitlines()[1]
    assert '"GRANTED"' in t01_auth and '"REJECTED"' in t02_auth and '"close_workorder"::request(' in close
    for arm, spec in VENDOR_ARMS.items():
        d = dest / arm
        tool_name, fields = spec["tool_name"], spec["output_fields"]
        m = copy.deepcopy(base_wo)
        tool = next(t for t in m["tools"] if t["name"] == "get_workorder")
        tool["name"] = tool_name
        for f, s in fields.items():
            assert f not in tool["outputSchema"]["properties"]
            tool["outputSchema"]["properties"][f] = s
        _dump_json(d / "manifests" / "wo.tools.json", m)
        _schema(d, d / "manifests" / "wo.tools.json", v2 / "manifests" / "authority.tools.json")
        entries = copy.deepcopy(base_entries)
        for e in entries:
            text = base_traces[e["id"]]
            if arm == "L3" and e["id"] == "t08_vendor_flag_only":
                text = text.replace('Drupe::Action::"get_workorder"::response(', f'Drupe::Action::"{tool_name}"::response(') \
                    .replace("Drupe::get_workorder_Output_WorkOrderResult", f"Drupe::{tool_name}_Output_WorkOrderResult")
                assert text != base_traces[e["id"]]
                e["note"] += f" (L3: vendor tool renamed {tool_name}; entity type renamed with it)"
            _write(d / e["file"], text)
        pos = _EVENT.format(ts=200, tool=tool_name, output=_vendor_output(tool_name, spec["positive"], "approved"), rid="g1")
        neg = _EVENT.format(ts=200, tool=tool_name, output=_vendor_output(tool_name, spec["negative"], "rejected"), rid="g1")
        held = [
            ("t15_vendor_enum_only", "deny", [pos.replace("@200", "@100"), close],
             f"vendor-only history: {tool_name}::response carrying the arm's positive value ({spec['positive']}, vendor_approval_status approved); no authority response. Contract: DENY (A5 i)"),
            ("t16_authority_rejected_vendor_positive", "deny", [t02_auth, pos, close],
             f"authority REJECTED/HUMAN at @100, vendor positive ({spec['positive']}) at @200. Contract: DENY (A5 ii)"),
            ("t17_authority_granted_vendor_negative", "allow", [t01_auth, neg, close],
             f"authority GRANTED/HUMAN at @100, vendor negative ({spec['negative']}, vendor_approval_status rejected) at @200. Contract: ALLOW (A5 iii)"),
        ]
        for tid, contract, lines, note in held:
            _write(d / "traces" / f"{tid}.log", "\n".join(lines) + "\n")
            entries.append({"id": tid, "file": f"traces/{tid}.log", "contract": contract, "note": note})
        _write_suite(d, entries, f"arm {arm} ({spec['note']}): the 14 base traces (copies) + 3 held-out traces in this arm's vendor encoding; contract unchanged")
        flag = "approved" if arm == "L4" else None   # L4's positive value is not approval-shaped; its mutant also binds the flag
        _write(d / "mutants" / "vendor_binding.dw", f"// mutant vendor_binding (arm {arm}): gold's close predicate bound to the vendor tool with the arm's positive value\n"
               + _vendor_predicate(tool_name, spec["positive"], flag))
        mutants = {"vendor_binding": {"killed_by": KILLED_VENDOR_BINDING, "text": f"close predicate bound to {tool_name}::response with {spec['positive']}" + (" and vendor_approval_status approved" if flag else "")}}
        stated = [v for f in fields.values() for v in f["enum"]]
        if arm in ("L2", "L4"):
            dec = spec["positive"].get("approval_outcome") or spec["positive"]["priority"]
            kind = spec["positive"].get("approver_type", "HUMAN")
            bl = GOLD.read_text().replace('output.decision: "GRANTED"', f'output.decision: "{dec}"').replace('output.approver_kind: "HUMAN"', f'output.approver_kind: "{kind}"')
            _write(d / "mutants" / "borrowed_literal.dw", f"// mutant borrowed_literal (arm {arm}): gold with the authority predicate using the vendor-stated value(s)\n" + bl)
            mutants["borrowed_literal"] = {"killed_by": KILLED_BORROWED, "text": f'authority predicate with output.decision "{dec}", output.approver_kind "{kind}"'}
            bl_note = "defined: the vendor states values the contract does not"
        else:
            bl_note = "not defined: the vendor-stated values are the contract's own, so a borrowed-literal mutant coincides with gold"
        _requirements(d, f"t01 requirements for arm {arm} (= base + held-out traces t15–t17, vendor_only_traces, evidence_vocabulary); scoring only",
                      [tool_name], stated, spec["approver_kind_fields"], ["t08_vendor_flag_only", "t15_vendor_enum_only"], held_out=True)
        entry = {"note": spec["note"], "vendor_edit": {"tool": "get_workorder", "tool_name": tool_name, "output_fields": fields,
                                                       "required_unchanged": True, "channel": "structure"},
                 "positive": spec["positive"], "negative": spec["negative"], "mutants": mutants, "borrowed_literal_note": bl_note}
        if arm == "L2":
            entry["marker_tokens"] = MARKER_TOKENS
            entry["marker_token_search"] = _marker_search()
        entry["sha256"] = _hashes(d)
        record["arms"][arm] = entry
    _dump_json(dest / "arms.json", record)
    return record


def main() -> None:
    rec = build(HERE / "arms")
    for arm, e in rec["arms"].items():
        print(arm, e["note"])
        for rel, h in e["sha256"].items():
            if rel.startswith(("manifests/", "schema/t01.dogwood.cedarschema")) or rel == "gold.dw":
                print("   ", h, rel)
    if "marker_token_search" in rec["arms"]["L2"]:
        print("L2 marker search:", rec["arms"]["L2"]["marker_token_search"])


if __name__ == "__main__":
    main()
