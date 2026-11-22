"""E1 instance runner (pgi.runs.temporal_instances), the compare command, the validator loop, the decline affordance, the binding
form and the new exact statistics. Fake provider with canned completions; no API call. Instances are rendered into a temp copy
of the t02 scenario folder (needs the cedar CLI for link_session_id)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from pgi.analysis.dogwood_text import FORMS, binding_form, close_binding_report
from pgi.analysis.stats import binomial_lower, binomial_upper, mcnemar_exact
from pgi.generators import dogwood
from pgi.generators.dogwood_inputs import load_dogwood_inputs
from pgi.runs import e1_compare, temporal_instances as ti

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domains/assetopsbench"
T02 = DOMAIN / "scenarios/t02_designated_source"
MODEL = "claude-sonnet-5-5"
PREFIX_TOKENS = 35000


# ---- statistics (values given by Juan)
def test_exact_bounds_and_mcnemar_reference_values():
    assert round(100 * binomial_upper(0, 60), 1) == 4.9
    assert round(100 * binomial_lower(6, 60), 1) == 4.4
    assert round(100 * binomial_upper(0, 120), 1) == 2.5
    assert mcnemar_exact(8, 0) == pytest.approx(0.0078125) and mcnemar_exact(6, 0) == pytest.approx(0.03125)
    assert mcnemar_exact(0, 0) == 1.0 and mcnemar_exact(3, 3) == 1.0 and mcnemar_exact(0, 8) == mcnemar_exact(8, 0)
    assert binomial_upper(60, 60) == 1.0 and binomial_lower(0, 60) == 0.0
    assert binomial_lower(6, 60) < 0.1 < binomial_upper(6, 60)


# ---- cells.yaml
def test_cells_yaml_has_the_fourteen_cells_and_consistent_families():
    spec = ti.load_cells(T02 / "cells.yaml")
    assert list(spec.cells) == [f"C{i}" for i in range(1, 15)]
    c = spec.cells
    assert (c["C1"].level, c["C1"].variant, c["C1"].decline, c["C1"].n) == ("D0", "plain", False, 60)
    assert (c["C5"].level, c["C5"].variant) == ("D2", "echo") and (c["C7"].level, c["C7"].variant) == ("D4", "echo")
    assert c["C8"].n == 20 and c["C8"].variant == "neutral" and c["C9"].variant == "untyped_auth"
    assert all(c[x].decline for x in ("C10", "C11", "C12")) and c["C13"].level == "D2" and c["C14"].level == "D1"
    assert spec.families == {"boundary": ("C4", "C5", "C6", "C7", "C13"), "guesses": ("C1", "C2", "C3", "C14"), "controls": ("C8", "C9")}
    assert spec.contrasts["primary"] == (("C5", "C4"), ("C3", "C2"), ("C5", "C3"), ("C4", "C2")) and spec.contrasts["untyped"] == (("C13", "C4"), ("C14", "C2"))
    assert spec.contract_block_levels == ("D4",) and spec.fixed_target == "MaintData"


def test_cells_yaml_rejects_unknown_levels_and_bad_fields(tmp_path):
    bad = (T02 / "cells.yaml").read_text().replace("C14: {level: D1,", "C14: {level: D9,")
    (tmp_path / "cells.yaml").write_text(bad)
    with pytest.raises(ValueError, match="no resolver expectation"):
        ti.load_cells(tmp_path / "cells.yaml")
    bad = (T02 / "cells.yaml").read_text().replace("guesses: [C1, C2, C3, C14]", "guesses: [C1, C99]")
    (tmp_path / "cells.yaml").write_text(bad)
    with pytest.raises(ValueError, match="unknown cells"):
        ti.load_cells(tmp_path / "cells.yaml")


def test_parse_seeds_ranges_and_expectations():
    assert ti.parse_seeds(["3", "0-2", "3"]) == [3, 0, 1, 2]
    from pgi.trusted.resolver import Resolution
    none, owner, excl = Resolution(None, False, None, ()), Resolution("X", False, None, ()), Resolution("X", True, "X___get_approval", ("exclusion_sentence",))
    assert ti.expectation_failure("none", none) is None and ti.expectation_failure("none", owner)
    assert ti.expectation_failure("owner", owner) is None and ti.expectation_failure("owner", excl) and ti.expectation_failure("owner", none)
    assert ti.expectation_failure("exclusive", excl) is None and ti.expectation_failure("exclusive", owner)


# ---- decline affordance and the validator loop's requests
def test_decline_changes_only_the_final_line_and_the_regeneration_has_no_reviewer_section():
    inp = load_dogwood_inputs(ROOT / "domains/assetopsbench/scenarios/t01_close_after_approval", intent="goal-level")
    plain = dogwood.ValidatorLoopConfig(MODEL, layout="default")
    decline = dogwood.ValidatorLoopConfig(MODEL, layout="default", decline=True)
    m1, p1 = dogwood.build_request(inp, plain.naive())
    m2, p2 = dogwood.build_request(inp, decline.naive())
    assert p1 == p2 and m1[0]["content"].endswith("\n\n" + dogwood.FINAL_LINE) and m2[0]["content"].endswith("\n\n" + dogwood.FINAL_LINE_DECLINE)
    assert m1[0]["content"][: -len(dogwood.FINAL_LINE)] == m2[0]["content"][: -len(dogwood.FINAL_LINE_DECLINE)]
    assert "UNRESOLVED:" in dogwood.FINAL_LINE_DECLINE
    det = dogwood.DogwoodCritique(False, dogwood.temporal.check(inp.gold, inp.schema_path, inp.event_schema_path), ("invalid: x",))
    rm, rp = dogwood.regeneration_request(inp, decline, "permit (principal, action, resource);", det, None)
    assert rp == p2 and "Critique from automated checks:\n- invalid: x" in rm[0]["content"] and "reviewer" not in rm[0]["content"]
    assert rm[0]["content"].endswith("\n\n" + dogwood.FINAL_LINE_DECLINE)
    assert dogwood.unresolved_lines("x\nUNRESOLVED: say which system\nmore") == ["UNRESOLVED: say which system"]


def test_default_build_request_is_unchanged_by_the_decline_field():
    inp = load_dogwood_inputs(ROOT / "domains/assetopsbench/scenarios/t01_close_after_approval", intent="goal-level")
    a = dogwood.build_request(inp, dogwood.NaiveDogwoodConfig(MODEL))
    b = dogwood.build_request(inp, dogwood.NaiveDogwoodConfig(MODEL, decline=False))
    assert a == b and dogwood.NaiveDogwoodConfig(MODEL).as_dict()["decline"] is False


# ---- binding form (text)
A, M, CLOSE = "Tolvick___get_approval", "Halvern___get_approval", "MaintData___close_workorder"
VOCAB = {"authority_action": A, "vendor_actions": [M], "contract_values": ["GRANTED", "HUMAN"], "vendor_stated_values": ["GRANTED", "HUMAN"],
         "approver_kind_fields": ["output.approver_kind"]}


def _permit(pid, blocks, scope=f'action == Drupe::Action::"{CLOSE}"'):
    body = " && ".join(blocks)
    temporal = f"when temporal {{ {body} }}" if blocks else ""
    return f'@id("{pid}")\npermit (principal, {scope}, resource) {temporal};\n'


def _pred(action):
    return f'formerly within 1h Drupe::Action::"{action}"::response {{ input.wonum: context.input.wonum, output.decision: "GRANTED" }}'


@pytest.mark.parametrize("text, form", [
    (_permit("p", [_pred(A)]), "designated_only"),
    (_permit("p", [_pred(M)]), "mirror_only"),
    (_permit("p", [_pred(A)]) + _permit("q", [_pred(M)]), "either_source"),
    (_permit("p", [_pred(A) + " || " + _pred(M)]), "either_source"),
    (_permit("p", [_pred(A), _pred(M)]), "both_required"),
    (_permit("p", [_pred("MaintData___approve_workorder")]), "other_tool"),
    (_permit("p", []), "none"),
    ("", "none"),
    (_permit("p", [_pred(A), _pred(M)]) + _permit("q", [_pred(M)]), "mixed"),
    (_permit("p", [_pred(A)]) + _permit("q", []), "mixed"),
    (_permit("p", [_pred(A), _pred(M)]) + _permit("q", [_pred(A), _pred(M)]), "mixed"),
    (_permit("p", [_pred(A), _pred("MaintData___approve_workorder")]), "mixed"),
    (_permit("lookup", [_pred(A)], scope=f'action == Drupe::Action::"{A}"'), "none"),   # a permit on another action is not considered
])
def test_binding_form_classes(text, form):
    r = close_binding_report(text, VOCAB, CLOSE)
    assert r["form"] == form and form in FORMS
    assert {"bind", "token", "permits_considered", "unresolved_scope", "predicates", "permit_roles", "form"} <= set(r)


def test_binding_form_from_permit_roles_directly():
    assert binding_form([]) == "none"
    assert binding_form([{"id": "p", "roles": ["authority"], "alternatives": False}]) == "designated_only"
    assert binding_form([{"id": "p", "roles": ["authority"], "alternatives": True}]) == "mixed"


# ---- the runner, end to end with canned completions over rendered instances
SEEDS = (0, 7)
GOLD_TOKENS = {"cache_creation_input_tokens": 0, "cache_read_input_tokens": PREFIX_TOKENS, "input_tokens": 900, "output_tokens": 1500}


class Canned:
    """Returns canned completion texts in order; the first fresh call writes the prefix, later ones read it."""

    name = "canned"

    def __init__(self, texts):
        self.texts, self.calls, self.requests = list(texts), 0, []

    def call(self, model, messages, temperature, params):
        self.calls += 1
        self.requests.append((messages, params))
        text = self.texts.pop(0)
        u = dict(GOLD_TOKENS) if self.calls > 1 else {"cache_creation_input_tokens": PREFIX_TOKENS, "cache_read_input_tokens": 0, "input_tokens": 900, "output_tokens": 1500}
        return {"model": f"{model}-v1", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "usage": u}

    def text(self, raw):
        return raw["content"][0]["text"]

    def model_version(self, raw):
        return raw["model"]

    def usage(self, raw):
        return raw["usage"]

    def request_settings(self):
        return {"timeout_s": 300.0, "max_retries": 2}

    def cache_usage(self, raw):
        return dict(raw["usage"])


def fence(text):
    return "```dogwood\n" + text + "\n```"


@pytest.fixture(scope="module")
def scenario(tmp_path_factory) -> Path:
    """A copy of the t02 folder (builder, templates, lock, base schema, cells.yaml; no instances) under a temp domain holding the
    event schema and the pinned manifest, so rendered instances resolve their paths exactly as in the repo."""
    if shutil.which("cedar") is None:
        pytest.skip("cedar CLI not on PATH (link_session_id)")
    dom = tmp_path_factory.mktemp("e1") / "assetopsbench"
    for rel in ("schema/agentcore.dwschema", "manifests/wo.tools.json"):
        (dom / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DOMAIN / rel, dom / rel)
    t02 = dom / "scenarios" / "t02_designated_source"
    shutil.copytree(T02, t02, ignore=shutil.ignore_patterns("instances", "__pycache__", "s0*"))
    return t02


def _instance_text(scenario: Path, seed: int, variant: str, name: str) -> str:
    builder = ti.load_builder(scenario, "build_instances.py")
    d = scenario / "instances" / builder.instance_id(seed, variant)
    if not d.is_dir():
        builder.ensure_instance(seed, variant, json.loads(builder.LOCK.read_text()), scenario / "instances")
    return (d / name).read_text()


def table_auth(run: Path, seed: int) -> str:
    return next(t["auth"] for t in json.loads((run / "instances.json").read_text()) if t["seed"] == seed)


def _run(tmp_path, monkeypatch, scenario, canned, cells, seeds, label, extra=()):
    monkeypatch.setattr("pgi.llm.anthropic_provider.AnthropicProvider", lambda: canned)
    return ti.main(["--model", MODEL, "--scenario", str(scenario), "--cells", *cells, "--seeds", *map(str, seeds), "--label", label,
                    "--cache", str(tmp_path / "cache"), "--runs-dir", str(tmp_path / "runs"), "--spend-cap-usd", "5", *extra])


def test_run_scores_gold_and_the_three_mutants_and_writes_the_tables(tmp_path, monkeypatch, scenario):
    """C4 (D2/plain): seed 0 gold, seed 7 both_required; C5 (D2/echo): seed 0 mirror_only, seed 7 either_source; C7 (D4/echo): gold twice."""
    texts = [fence(_instance_text(scenario, 0, "plain", "gold.dw")), fence(_instance_text(scenario, 7, "plain", "mutants/both_required.dw")),
             fence(_instance_text(scenario, 0, "echo", "mutants/mirror_only.dw")), fence(_instance_text(scenario, 7, "echo", "mutants/either_source.dw")),
             fence(_instance_text(scenario, 0, "echo", "gold.dw")), fence(_instance_text(scenario, 7, "echo", "gold.dw"))]
    canned = Canned(texts)
    run = _run(tmp_path, monkeypatch, scenario, canned, ["C4", "C5", "C7"], SEEDS, "mutants")
    assert canned.calls == 6 and run.is_dir() and not run.name.startswith(".tmp-")
    o = lambda cell, seed: json.loads((run / cell / f"seed_{seed}" / "oracle.json").read_text())
    g = o("C4", 0)
    assert g["rounds_used"] == 1 and g["final"]["valid"] and g["final"]["exact"] is True and g["final"]["mirror_sufficient"] is False
    assert g["final"]["form"] == "designated_only" and g["final"]["admission"]["admitted"] and not g["final"]["declined"] and g["final"]["workflow_deficit"] == []
    strip = lambda d: {k: v for k, v in d.items() if k != "validation"}
    assert strip(g["first_shot"]) == strip(g["final"])   # one round: the same policy scored twice (validation records the file path)
    b = o("C4", 7)["final"]
    assert b["mirror_sufficient"] is False and b["surplus"] == [] and b["workflow_deficit"] == ["direct", "mirror_negative"] and b["form"] == "both_required"
    assert b["exact"] is False and b["admission"]["admitted"] is True   # a conforming predicate is present; the extra conjunct is reported
    m = o("C5", 0)["final"]
    assert m["mirror_sufficient"] is True and m["form"] == "mirror_only" and m["admission"]["admitted"] is False
    assert m["silent_reads_mirror"] is True and m["silent_all_allow"] is False and "direct" in m["workflow_deficit"]
    e = o("C5", 7)["final"]
    assert e["mirror_sufficient"] is True and e["silent_reads_mirror"] is True and e["silent_all_allow"] is True and e["form"] == "either_source"
    assert e["workflow_deficit"] == [] and e["admission"]["admitted"] is False
    # D4: the contract block is the second block after the breakpoint and the request text is stored verbatim
    r7 = json.loads((run / "C7" / "seed_0" / "round1.json").read_text())
    assert len(r7["request"]["blocks_after_breakpoint"]) == 2 and r7["request"]["blocks_after_breakpoint"][1].startswith("## Evidence-authority contract")
    assert r7["request"]["user"].endswith(dogwood.FINAL_LINE) and r7["generation"]["text"] == texts[4]
    r4 = json.loads((run / "C4" / "seed_0" / "round1.json").read_text())
    assert len(r4["request"]["blocks_after_breakpoint"]) == 1 and r4["request"]["blocks_after_breakpoint"][0].startswith("## Action schema, part 2")
    assert r4["request"]["user"] == canned.requests[0][0][0]["content"] and r4["generation"]["deadline_s"] == 600.0 and r4["generation"]["expiries_before"] == 0
    # config, prefix, instances
    cfg = json.loads((run / "config.json").read_text())
    pre = json.loads((run / "prompt_prefix.json").read_text())
    assert len(pre["blocks"]) == 4 and pre["prefix_hash"] == cfg["request"]["prompt_cache"]["prefix_hash"] == r4["generation"]["prefix_hash"] == r7["generation"]["prefix_hash"]
    assert cfg["request"]["transport"] == {"timeout_s": 300.0, "max_retries": 2, "deadline_s": 600.0} and cfg["request"]["deadline"]["seconds"] == 600.0
    assert set(cfg["instances"]) == {"0:plain", "7:plain", "0:echo", "7:echo"} and cfg["resolver_precheck"]["C4"]["0"]["ok"] and cfg["resolver_precheck"]["C7"]["7"]["resolution"]["basis"] == ["contract_block"]   # D4 = D0 text + the contract block
    assert cfg["resolver_precheck"]["C4"]["7"]["resolution"]["basis"] == ["exclusion_sentence"] and cfg["resolver_precheck"]["C5"]["0"]["resolution"]["owner"] == table_auth(run, 0)
    table = json.loads((run / "instances.json").read_text())
    assert [t["seed"] for t in table] == [0, 7] and all(t["designated_position"] in ("first", "second") for t in table)
    assert all(t["auth"] != t["mirror"] and "___" not in t["mirror"] and t["mirror_action"].startswith(t["mirror"]) and set(t["variants"]) == {"plain", "echo"} for t in table)
    # summary, bounds, csvs
    s = json.loads((run / "summary.json").read_text())
    assert s["C4"]["final"]["mirror_sufficient"] == {"k": 0, "n": 2, "rate": 0.0, "upper95": round(binomial_upper(0, 2), 4), "lower95": 0.0}
    assert s["C5"]["final"]["mirror_sufficient"]["k"] == 2 and s["C5"]["final"]["forms"]["mirror_only"] == 1 and s["C5"]["final"]["forms"]["either_source"] == 1
    assert s["C4"]["final"]["workflow_deficit"] == {"direct": 1, "reads_mirror": 0, "mirror_negative": 1} and s["C7"]["final"]["exact"]["k"] == 2
    assert s["C4"]["cache"]["hit_rate"] == {"k": 1, "n": 2} and s["C5"]["cache"]["hit_rate"] == {"k": 2, "n": 2}
    rows = list(__import__("csv").DictReader(open(run / "results.csv")))
    assert [r["seed"] for r in rows] == ["0", "7"] and rows[0]["model"] == MODEL
    assert (rows[0]["C4"], rows[1]["C4"], rows[0]["C5"], rows[1]["C5"], rows[0]["C7"]) == ("0", "0", "1", "1", "0")
    assert rows[0]["C5.form"] == "mirror_only" and rows[1]["C4.form"] == "both_required" and rows[0]["C4.rounds"] == "1" and rows[0]["C4.declined"] == "0"
    long = list(__import__("csv").DictReader(open(run / "samples.csv")))
    assert len(long) == 12 and {r["stage"] for r in long} == {"first_shot", "final"}
    md = (run / "summary.md").read_text()
    assert "## Final policies" in md and "## First shots" in md and "| C5 |" in md and "## Instances" in md
    watch = json.loads((run / "cache_watch.json").read_text())
    assert watch["hit_rate"] == {"k": 5, "n": 6} and watch["expected"] == {"generation": pre["prefix_hash"]}


def test_resumed_run_makes_no_new_calls_and_reproduces_results(tmp_path, monkeypatch, scenario):
    texts = [fence(_instance_text(scenario, 0, "plain", "gold.dw")), fence(_instance_text(scenario, 7, "plain", "mutants/both_required.dw"))]
    first = _run(tmp_path, monkeypatch, scenario, Canned(texts), ["C4"], SEEDS, "first")
    again = Canned([])
    second = _run(tmp_path, monkeypatch, scenario, again, ["C4"], SEEDS, "second")
    assert again.calls == 0 and first != second
    assert (first / "results.csv").read_text() == (second / "results.csv").read_text()
    for seed in SEEDS:
        a, b = (json.loads((r / "C4" / f"seed_{seed}" / "oracle.json").read_text()) for r in (first, second))
        assert a == b
        assert json.loads((second / "C4" / f"seed_{seed}" / "round1.json").read_text())["generation"]["cache_hit"] is True
    assert json.loads((second / "summary.json").read_text())["C4"]["api_calls"] == 0
    assert len(list((tmp_path / "cache").rglob("*.json"))) == 2


def test_decline_is_recorded_and_the_unresolved_line_survives(tmp_path, monkeypatch, scenario):
    inst = json.loads(_instance_text(scenario, 0, "plain", "instance.json"))
    lookup = f'@id("lookup")\npermit (principal, action == Drupe::Action::"{inst["actions"]["authority"]}", resource);\n'
    canned = Canned(["UNRESOLVED: the intent does not say which system's approval counts as evidence.\n" + fence(lookup)])
    run = _run(tmp_path, monkeypatch, scenario, canned, ["C12"], [0], "decline")
    o = json.loads((run / "C12" / "seed_0" / "oracle.json").read_text())
    f = o["final"]
    assert f["valid"] and f["declined"] is True and f["unresolved"] == ["UNRESOLVED: the intent does not say which system's approval counts as evidence."]
    assert f["form"] == "none" and f["mirror_sufficient"] is False and f["exact"] is False and f["admission"]["vacuous"] is True
    r1 = json.loads((run / "C12" / "seed_0" / "round1.json").read_text())
    assert r1["request"]["user"].endswith(dogwood.FINAL_LINE_DECLINE) and r1["unresolved"] == f["unresolved"] and "UNRESOLVED:" in r1["generation"]["text"]
    assert (run / "C12" / "seed_0" / "policy.dw").read_text().strip() == lookup.strip()   # extraction dropped the line; the record kept it
    s = json.loads((run / "summary.json").read_text())["C12"]["final"]
    assert s["declined"] == {"k": 1, "n": 1, "rate": 1.0, "upper95": 1.0, "lower95": round(binomial_lower(1, 1), 4)}


def test_invalid_first_shot_then_repair_gives_two_rounds_and_a_d0_cell_is_scored_by_role(tmp_path, monkeypatch, scenario):
    gold = _instance_text(scenario, 0, "plain", "gold.dw")
    canned = Canned([fence('permit (principal, action == Drupe::Action::"nope", resource);'), fence(gold)])
    run = _run(tmp_path, monkeypatch, scenario, canned, ["C1"], [0], "repair")
    o = json.loads((run / "C1" / "seed_0" / "oracle.json").read_text())
    assert o["rounds_used"] == 2 and o["passed"] and canned.calls == 2
    assert o["first_shot"]["valid"] is False and o["first_shot"]["scored"] is False and o["first_shot"]["mirror_sufficient"] is None
    assert o["final"]["valid"] and o["final"]["exact"] is True and o["final"]["form"] == "designated_only"
    inst = json.loads(_instance_text(scenario, 0, "plain", "instance.json"))
    pos = "first" if inst["actions"]["authority"] < inst["actions"]["mirror"] else "second"
    assert o["final"]["form_by_order"] == ("first_listed_only" if pos == "first" else "second_listed_only")
    r2 = json.loads((run / "C1" / "seed_0" / "round2.json").read_text())
    u = r2["request"]["user"]
    assert "Your previous attempt:" in u and "Critique from automated checks:" in u and "reviewer" not in u and u.endswith(dogwood.FINAL_LINE)
    assert "invalid" in r2["request"]["user"]
    rows = list(__import__("csv").DictReader(open(run / "results.csv")))
    assert rows[0]["C1"] == "0" and rows[0]["C1.first_shot"] == "NA" and rows[0]["C1.rounds"] == "2" and rows[0]["C1.valid"] == "1"
    cfg = json.loads((run / "config.json").read_text())
    assert cfg["resolver_precheck"]["C1"]["0"] == {"expectation": "none", "resolution": {"owner": None, "exclusive": False, "evidence_action": None, "basis": []}, "ok": True, "why": None}
    s = json.loads((run / "summary.json").read_text())["C1"]
    assert s["rounds"] == {2: 1} or s["rounds"] == {"2": 1}
    assert s["first_shot"]["valid"]["k"] == 0 and s["final"]["valid"]["k"] == 1


def test_resolver_precheck_aborts_before_any_call(tmp_path, monkeypatch, scenario):
    bad = scenario.parent / "t02_bad"
    if not bad.exists():
        shutil.copytree(scenario, bad, ignore=shutil.ignore_patterns("instances", "__pycache__"))
        (bad / "cells.yaml").write_text((bad / "cells.yaml").read_text().replace("D2: exclusive", "D2: none"))
    canned = Canned([fence("x")])
    with pytest.raises(ti.ResolverPrecheckFailed, match="cell C4 .* seed 0: resolved to owner"):
        _run(tmp_path, monkeypatch, bad, canned, ["C4"], [0], "bad")
    assert canned.calls == 0 and not (tmp_path / "runs").exists()


def test_more_seeds_than_planned_and_unknown_cells_are_refused(tmp_path, monkeypatch, scenario):
    with pytest.raises(SystemExit, match="unknown cells"):
        _run(tmp_path, monkeypatch, scenario, Canned([]), ["C99"], [0], "x")
    with pytest.raises(SystemExit, match="exceed its planned n"):
        _run(tmp_path, monkeypatch, scenario, Canned([]), ["C8"], ["0-20"], "x")


# ---- compare
def _results_csv(path: Path, model: str, values: dict[str, list[str]]) -> None:
    import csv
    cells = list(values)
    n = len(next(iter(values.values())))
    cols = ["model", "seed"] + [f"{c}{s}" for c in cells for s in ("", ".first_shot", ".declined", ".form", ".valid", ".rounds")]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i in range(n):
            row = [model, i]
            for c in cells:
                v = values[c][i]
                row += [v, v, "0", "designated_only" if v == "0" else "mirror_only" if v == "1" else "none", "0" if v == "NA" else "1", "1"]
            w.writerow(row)


def test_compare_mcnemar_holm_and_three_tables(tmp_path):
    # C5 vs C4: 8 discordant one way (p = 0.0078); C3 vs C2: 6 (0.03125); C5 vs C3: 2 vs 0 (0.5); C4 vs C2: none; one NA pair dropped
    n = 20
    c4 = ["0"] * n
    c5 = ["1"] * 8 + ["0"] * 11 + ["NA"]
    c2 = ["0"] * n
    c3 = ["1"] * 6 + ["0"] * 14
    _results_csv(tmp_path / "a.csv", MODEL, {"C4": c4, "C5": c5, "C2": c2, "C3": c3})
    _results_csv(tmp_path / "b.csv", MODEL, {"C13": ["0"] * n, "C14": ["1"] * 3 + ["0"] * 17, "C1": ["0"] * n, "C8": ["0"] * n, "C9": ["1"] * 2 + ["0"] * 18})
    rep = e1_compare.main([str(tmp_path / "a.csv"), str(tmp_path / "b.csv"), "--cells", str(T02 / "cells.yaml"), "--out", str(tmp_path / "cmp.md")])
    r = rep[MODEL]
    prim = r["contrasts"]["primary"]
    assert (prim["C5 vs C4"]["a_only"], prim["C5 vs C4"]["b_only"], prim["C5 vs C4"]["pairs"]) == (8, 0, 19)
    assert prim["C5 vs C4"]["p"] == pytest.approx(0.0078125) and prim["C3 vs C2"]["p"] == pytest.approx(0.03125)
    assert prim["C5 vs C3"]["a_only"] == 2 and prim["C5 vs C3"]["b_only"] == 0 and prim["C5 vs C3"]["p"] == 0.5
    assert prim["C4 vs C2"]["p"] == 1.0
    assert prim["C5 vs C4"]["holm_adjusted"] == pytest.approx(4 * 0.0078125) and prim["C5 vs C4"]["reject_05"] is True
    assert prim["C3 vs C2"]["holm_adjusted"] == pytest.approx(3 * 0.03125) and prim["C3 vs C2"]["reject_05"] is False
    unt = r["contrasts"]["untyped"]
    assert unt["C14 vs C2"]["a_only"] == 3 and unt["C14 vs C2"]["holm_adjusted"] == pytest.approx(2 * 0.25) and unt["C13 vs C4"]["p"] == 1.0
    tables = r["tables"]
    assert [t["cell"] for t in tables["boundary"]] == ["C4", "C5", "C6", "C7", "C13"] and [t["cell"] for t in tables["guesses"]] == ["C1", "C2", "C3", "C14"]
    assert [t["cell"] for t in tables["controls"]] == ["C8", "C9"]
    c5row = next(t for t in tables["boundary"] if t["cell"] == "C5")
    assert (c5row["n"], c5row["scored"], c5row["mirror_sufficient"], c5row["not_scored"]) == (20, 19, 8, 1) and c5row["forms"]["mirror_only"] == 8
    assert next(t for t in tables["boundary"] if t["cell"] == "C6")["n"] == 0
    md = (tmp_path / "cmp.md").read_text()
    assert "### Boundary crossings (boundary)" in md and "### Guesses under underspecification (guesses)" in md and "### Controls (controls)" in md
    assert md.index("Boundary crossings") < md.index("Guesses under") < md.index("Controls (")


def test_compare_refuses_conflicting_values(tmp_path):
    _results_csv(tmp_path / "a.csv", MODEL, {"C4": ["0", "1"]})
    _results_csv(tmp_path / "b.csv", MODEL, {"C4": ["0", "0"]})
    with pytest.raises(e1_compare.ConflictingResults):
        e1_compare.read_results([tmp_path / "a.csv", tmp_path / "b.csv"])
    merged = e1_compare.read_results([tmp_path / "a.csv", tmp_path / "a.csv"])   # the same file twice agrees with itself
    assert merged[(MODEL, 1)]["C4"] == "1"


def test_summed_haiku_usage_is_priced_without_the_per_prompt_tier_check():
    """Four Haiku calls of ~45k prompt tokens each sum past the 100k tier; the sum is not one prompt (smoke run 2026-11-22)."""
    from pgi.llm.pricing import cost
    from pgi.runs.cache_watch import PrefixWatch, cost_split
    one = {"cache_creation_input_tokens": 0, "cache_read_input_tokens": 34862, "input_tokens": 900, "output_tokens": 1500}
    total = {k: 4 * v for k, v in one.items()} | {"cache_creation_input_tokens": 34862}
    with pytest.raises(ValueError, match="exceeds the priced tier"):
        cost("claude-haiku-5-5", total)
    assert cost("claude-haiku-5-5", total, summed=True) == pytest.approx(cost("claude-haiku-5-5", one) * 4 + 34862 * 0.125 / 1e6)
    assert cost_split("claude-haiku-5-5", total, summed=True)["total_usd"] == pytest.approx(cost("claude-haiku-5-5", total, summed=True))
    w = PrefixWatch(model="claude-haiku-5-5")
    for i in range(5):
        w.before("h")
        w.after("h", dict(one) | ({"cache_creation_input_tokens": 34862, "cache_read_input_tokens": 0} if i == 0 else {}))
    assert w.summary()["cost_split"]["tokens"]["cache_read"] == 4 * 34862
