"""t02_designated_source foundations (Phase 3, E1; zero API): the seeded instance builder, the trusted resolver, the 19-trace
contract, mutation adequacy, admission, determinism and the lock file. Oracle: Dogwood interpreter via pgi.oracle.temporal under
the AWS-shaped event schema; behaviour over traces, never policy text (the admission checker is the one text check, labelled)."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import pytest
import yaml

from pgi.analysis.admission import check_policy, load_catalogue
from pgi.generators.dogwood import NaiveDogwoodConfig, build_request
from pgi.generators.dogwood_inputs import load_dogwood_inputs, load_snapshot, snapshot
from pgi.generators.schema_split import split_schema
from pgi.llm.prefix import prefix_hash
from pgi.oracle import temporal
from pgi.schemagen import generate_dogwood
from pgi.trusted.resolver import Registry, Resolution, ResolverError, owner_of, resolve

ROOT = Path(__file__).resolve().parents[1]
T02 = ROOT / "domains" / "assetopsbench" / "scenarios" / "t02_designated_source"
EVENTS = ROOT / "domains" / "assetopsbench" / "schema" / "agentcore.dwschema"
sys.path.insert(0, str(T02))
import build_instances as bi  # noqa: E402
import intents  # noqa: E402
import registry  # noqa: E402
from names import MAINT_TARGET, POOL  # noqa: E402

needs_cedar = pytest.mark.skipif(shutil.which("cedar") is None, reason="cedar CLI not on PATH (link_session_id)")
SAMPLE = [(0, "plain"), (7, "echo"), (42, "neutral"), (1000, "untyped_auth")]   # all four variants, both vocabularies, three paraphrases
RESOLVER_SEEDS = list(range(12)) + list(range(1000, 1004))
WO_TOOLS = [t["name"] for t in json.loads(bi.WO_PIN.read_text())["tools"]]


def targets(inst: bi.Instance, variant: str) -> dict[str, list[str]]:
    """Target prefix -> tool names, the resolver's view of the gateway (prefixes only; never descriptions)."""
    return {MAINT_TARGET: WO_TOOLS} | {server: [t["name"] for t in ts] for server, ts in bi.tools(inst, variant).items()}


@pytest.fixture(scope="module")
def rendered(tmp_path_factory) -> dict[str, dict]:
    if shutil.which("cedar") is None:
        pytest.skip("cedar CLI not on PATH (link_session_id)")
    # the instance's scenario.yaml paths are relative to the t02 folder (its "domain"), so mirror that layout under tmp
    dom = tmp_path_factory.mktemp("t02") / "assetopsbench"
    t02 = dom / "scenarios" / "t02_designated_source"
    for src, rel in ((EVENTS, "schema/agentcore.dwschema"), (bi.WO_PIN, "manifests/wo.tools.json")):
        (dom / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dom / rel)
    (t02 / "schema").mkdir(parents=True)
    shutil.copyfile(bi.BASE_SCHEMA, t02 / "schema" / bi.BASE_SCHEMA.name)
    out = {}
    for seed, variant in SAMPLE:
        inst = bi.instance(seed)
        d = t02 / "instances" / bi.instance_id(seed, variant)
        rec = bi.render(inst, variant, d)
        out[rec["id"]] = {"inst": inst, "variant": variant, "dir": d, "record": rec}
    return out


# ---- draws and the pool
def test_draws_are_deterministic_and_cover_the_design():
    seen_auth_first, vocabs, paraphrases = set(), set(), set()
    for seed in bi.LOCK_SEEDS:
        a, b = bi.instance(seed), bi.instance(seed)
        assert a == b and a.auth != a.mirror and {a.auth, a.mirror} <= set(POOL)
        vocabs.add(a.vocab)
        paraphrases.add(a.paraphrase)
        seen_auth_first.add(a.auth < a.mirror)
    assert vocabs == {0, 1} and paraphrases == {0, 1, 2} and seen_auth_first == {True, False}
    assert bi.instance(0).seed == 0 and bi.instance_id(0, "plain") == "s0000-plain"
    with pytest.raises(ValueError):
        bi.tools(bi.instance(0), "bogus")


def test_d0_paraphrase_0_is_the_goal_level_intent_and_levels_nest():
    assert intents.D0[0] == (ROOT / "domains/assetopsbench/scenarios/t01_close_after_approval/intent.goal-level.md").read_text()
    inst = bi.instance(3)
    texts = bi.intent_texts(inst)
    assert texts["D4"] == texts["D0"] and texts["D1"].startswith(texts["D0"]) and texts["D2"].startswith(texts["D1"]) and texts["D3"].startswith(texts["D2"])
    assert inst.auth not in texts["D0"] and inst.auth in texts["D1"] and inst.mirror not in texts["D3"]
    assert f"`{inst.auth}___get_approval`" in texts["D3"] and f"`{inst.auth}___get_approval`" not in texts["D2"]
    assert inst.decisions[0] in texts["D3"] and inst.decisions[0] not in texts["D2"]


# ---- toolchain facts re-verified on the pinned pydogwood (the builder relies on each)
def test_toolchain_facts(tmp_path):
    inst = bi.instance(0)
    plain, paths = bi.generated_schema(inst, "plain", tmp_path / "p")
    assert f'action "{MAINT_TARGET}___close_workorder"' in plain and f'action "{inst.auth}___get_approval"' in plain   # prefixed names generate
    reordered = generate_dogwood([*reversed(list(paths.values())), bi.WO_PIN], targets={bi.WO_PIN: MAINT_TARGET} | {p: s for s, p in paths.items()})
    assert reordered == plain                                                                                          # sorted output: manifest order has no effect
    assert bi.output_types(plain, f"{inst.auth}___get_approval", ["decision", "approver_kind"]) == {"decision": "decision", "approver_kind": "approver_kind"}
    assert bi.output_types(plain, f"{inst.mirror}___get_approval", ["decision"]) == {"decision": "decision"}             # same name + members: one shared entity
    neutral, _ = bi.generated_schema(inst, "neutral", tmp_path / "n")
    assert bi.output_types(neutral, f"{inst.auth}___get_approval", ["decision"]) == {"decision": f"{inst.auth}___get_approval_Output_decision"}
    untyped, _ = bi.generated_schema(inst, "untyped_auth", tmp_path / "u")
    assert bi.output_types(untyped, f"{inst.auth}___get_approval", ["decision"]) == {"decision": None}                  # plain String
    assert bi.output_types(untyped, f"{inst.mirror}___get_approval", ["decision"]) == {"decision": f"{inst.mirror}___get_approval_Output_decision"}
    base = bi.BASE_GENERATED.read_text()
    for text in (plain, neutral, untyped):
        split_schema(text, base)                                                                                          # every MaintData declaration unchanged
    assert bi.mutation_result_type(plain) == f"{MAINT_TARGET}___approve_workorder_Output_WorkOrderMutationResult"


@needs_cedar
def test_base_schema_is_the_committed_build_output(tmp_path):
    hashes = bi.build_base_schema(tmp_path)
    assert hashes == {bi.BASE_GENERATED.name: bi.sha(bi.BASE_GENERATED), bi.BASE_SCHEMA.name: bi.sha(bi.BASE_SCHEMA)}
    assert f'action "{MAINT_TARGET}___close_workorder"' in bi.BASE_SCHEMA.read_text() and "sessionId" in bi.BASE_SCHEMA.read_text()


# ---- the resolver (trusted inputs only)
@pytest.mark.parametrize("seed", RESOLVER_SEEDS)
@pytest.mark.parametrize("variant", bi.VARIANTS)
def test_resolver_required_results_per_level(seed, variant):
    inst = bi.instance(seed)
    tg, texts, action = targets(inst, variant), bi.intent_texts(inst), f"{inst.auth}___get_approval"
    r = lambda level, cat=None: resolve(texts[level], tg, registry.REGISTRY, fixed_targets=[MAINT_TARGET], catalogue=cat)
    assert r("D0") == Resolution(None, False, None, ())
    assert r("D1") == Resolution(inst.auth, False, None, ())
    assert r("D2") == Resolution(inst.auth, True, action, ("exclusion_sentence",))
    assert r("D3") == Resolution(inst.auth, True, action, ("exclusion_sentence", "action_sentence"))
    assert r("D4", bi.catalogue(inst)) == Resolution(None, True, action, ("contract_block",))
    # echo resolves exactly like plain: the mirror's tool name never enters
    if variant != "plain":
        plain = targets(inst, "plain")
        for level in intents.LEVELS:
            assert resolve(texts[level], tg, registry.REGISTRY, fixed_targets=[MAINT_TARGET], catalogue=bi.catalogue(inst) if level == "D4" else None) == \
                resolve(texts[level], plain, registry.REGISTRY, fixed_targets=[MAINT_TARGET], catalogue=bi.catalogue(inst) if level == "D4" else None)


def test_resolver_edge_cases():
    inst = bi.instance(5)
    tg, texts = targets(inst, "plain"), bi.intent_texts(inst)
    excl = registry.EXCLUSION_SENTENCES[inst.paraphrase].replace("{AUTH}", inst.auth)
    assert excl in texts["D2"]
    without = texts["D2"].replace(excl + "\n", "")
    assert without == texts["D1"] and resolve(without, tg, registry.REGISTRY, fixed_targets=[MAINT_TARGET]) == Resolution(inst.auth, False, None, ())
    both = texts["D2"] + f"\n{inst.mirror} also keeps a copy.\n"
    assert resolve(both, tg, registry.REGISTRY, fixed_targets=[MAINT_TARGET]) == Resolution(None, False, None, ())
    assert owner_of(texts["D1"], tg, [MAINT_TARGET]) == inst.auth and owner_of(texts["D0"], tg, [MAINT_TARGET]) is None
    # the fixed target is never an owner, and `Name___tool` is not a mention of Name
    assert owner_of(f"Close through {MAINT_TARGET}.", tg, [MAINT_TARGET]) is None
    assert owner_of(f"Use `{inst.auth}___get_approval`.", tg, [MAINT_TARGET]) is None
    assert owner_of(texts["D1"].replace(inst.auth, inst.auth.lower()), tg, [MAINT_TARGET]) is None   # case-sensitive
    # a reworded exclusion is free text: certified sentences only
    reworded = texts["D1"] + f"Only {inst.auth}'s own answer counts, nothing another system shows.\n"
    assert resolve(reworded, tg, registry.REGISTRY, fixed_targets=[MAINT_TARGET]).exclusive is False
    # disagreement: the contract names the mirror's action while the exclusion sentence names the owner
    cat = bi.catalogue(inst) | {"evidence": {"action": f"{inst.mirror}___get_approval", "kind": "response", "max_window": "1h"}}
    with pytest.raises(ResolverError, match="name"):
        resolve(texts["D2"], tg, registry.REGISTRY, fixed_targets=[MAINT_TARGET], catalogue=cat)
    # a catalogue alone (D4) with a malformed evidence entry is not exclusive
    assert resolve(texts["D0"], tg, registry.REGISTRY, fixed_targets=[MAINT_TARGET], catalogue={"evidence": {}}) == Resolution(None, False, None, ())


def test_registry_is_validated_and_hashed():
    assert re.fullmatch(r"[0-9a-f]{64}", registry.REGISTRY.sha256())
    assert registry.REGISTRY.sha256() == Registry(registry.EXCLUSION_SENTENCES, registry.ACTION_SENTENCE).sha256()   # the source path is not hashed
    assert registry.REGISTRY.sha256() != Registry(registry.EXCLUSION_SENTENCES[:2], registry.ACTION_SENTENCE).sha256()
    with pytest.raises(ValueError, match="exactly once"):
        Registry(("no placeholder here.",), registry.ACTION_SENTENCE)
    with pytest.raises(ValueError, match="action id"):
        Registry(registry.EXCLUSION_SENTENCES, "The evidence comes from {AUTH}.")
    for s in registry.EXCLUSION_SENTENCES:
        assert "get_approval" not in s and "decision" not in s and "approver" not in s     # no tool, field or value name below D3


# ---- rendered instances
def test_rendered_instance_loads_as_a_scenario_and_snapshots(rendered, tmp_path):
    for iid, r in rendered.items():
        inp = load_dogwood_inputs(r["dir"])
        assert inp.servers == (MAINT_TARGET, r["inst"].auth, r["inst"].mirror) and inp.manifest_paths[0].read_bytes() == bi.WO_PIN.read_bytes()
        assert inp.schema_base_text == bi.BASE_SCHEMA.read_text() and inp.event_schema_text == EVENTS.read_text() and inp.catalogue is not None
        for level in intents.LEVELS:
            assert load_dogwood_inputs(r["dir"], intent=level).intent == bi.intent_texts(r["inst"])[level]
        snap = snapshot(load_dogwood_inputs(r["dir"], intent="D2"), tmp_path / iid)
        assert load_snapshot(tmp_path / iid).hashes == snap.hashes and (tmp_path / iid / "schema_base" / bi.BASE_SCHEMA.name).is_file()


def test_gold_agrees_with_the_contract_and_every_mutant_is_killed_as_recorded(rendered):
    for iid, r in rendered.items():
        d = r["dir"]
        suite = temporal.load_suite(d / "traces.yaml")
        assert len(suite.ids) == 19 and sum(suite.contract.values()) == 5 and {t[:1] for t in suite.ids} == {"P", "M", "N"}
        mut = {p.stem: p for p in sorted((d / "mutants").glob("*.dw"))}
        assert set(mut) == set(bi.MUTANTS)
        rep = temporal.require_adequate(d / "gold.dw", mut, suite, d / "schema" / "t02.dogwood.cedarschema", EVENTS)
        assert rep.gold_allowed == {t for t, a in suite.contract.items() if a}
        assert {n: sorted(v) for n, v in rep.disagreements.items()} == r["record"]["mutants_expected_kills"], iid
        # the mirror-sufficient set is exactly what the mirror-only and either-source mutants newly allow
        for n in ("mirror_only", "either_source"):
            allowed = temporal.allowed(mut[n], suite, d / "schema" / "t02.dogwood.cedarschema", EVENTS)
            assert set(bi.MIRROR_SUFFICIENT) <= allowed and not allowed & {t for t in suite.ids if t.startswith("N")}


def test_timestamps_are_non_negative_and_the_close_is_last(rendered):
    for r in rendered.values():
        for p in sorted((r["dir"] / "traces").glob("*.log")):
            lines = p.read_text().splitlines()
            stamps = [int(re.match(r"^@(-?\d+) ", ln).group(1)) for ln in lines]
            assert all(s >= 0 for s in stamps) and stamps == sorted(stamps) and len(set(stamps)) == len(stamps), p.name
            assert f'"{bi.CLOSE}"::request(' in lines[-1]
            if p.stem in ("M5_authority_expired_mirror_fresh", "N5_expired"):
                assert stamps[0] == 0 and stamps[-1] == 4000
            else:
                assert stamps[-1] == 600


def test_admission_admits_gold_and_rejects_mirror_only_and_either_source(rendered):
    for r in rendered.values():
        d = r["dir"]
        cat, schema = load_catalogue(d / "admission.catalogue.yaml"), (d / "schema" / "t02.dogwood.cedarschema").read_text()
        g = check_policy((d / "gold.dw").read_text(), cat, schema)
        assert g["admitted"] and not g["vacuous"]
        for n in ("mirror_only", "either_source"):
            v = check_policy((d / "mutants" / f"{n}.dw").read_text(), cat, schema)
            assert not v["admitted"] and any("not " in x for x in v["reasons"]), (n, v["reasons"])
        assert cat["protected_action"] == bi.CLOSE and cat["evidence"]["action"] == f"{r['inst'].auth}___get_approval"


def test_requirements_catalogue_and_record_are_consistent(rendered):
    for r in rendered.values():
        d, rec = r["dir"], r["record"]
        inp = load_dogwood_inputs(d)
        from pgi.generators.dogwood_inputs import load_requirements
        reqs = load_requirements(inp.requirements, temporal.load_suite(inp.traces_yaml))
        assert reqs.workflows == {k: tuple(v) for k, v in bi.WORKFLOWS.items()} and set(reqs.vendor_only) == set(bi.MIRROR_SUFFICIENT)
        assert reqs.vocabulary["authority_action"] == rec["actions"]["authority"] and reqs.vocabulary["vendor_actions"] == [rec["actions"]["mirror"]]
        assert reqs.prerequisite == ("M6_authority_request_errored_mirror_positive", 0)
        assert rec["registry_sha256"] == registry.REGISTRY.sha256() and rec["base_schema_sha256"] == bi.sha(bi.BASE_SCHEMA)
        if r["variant"] in ("plain", "echo"):
            assert rec["shared_enum_types"] == ["approver_kind", "decision"]
        else:
            assert rec["shared_enum_types"] == []
        if r["variant"] == "untyped_auth":
            assert rec["enum_types"]["authority"] == {"decision": None, "approver_kind": None} and '"GRANTED"' in (d / "gold.dw").read_text() or '"ACCEPTED"' in (d / "gold.dw").read_text()


def test_split_layout_renders_one_prefix_over_the_rendered_instances(rendered):
    hashes, part2 = set(), []
    for r in rendered.values():
        for level in intents.LEVELS:
            inp = load_dogwood_inputs(r["dir"], intent=level)
            _, params = build_request(inp, NaiveDogwoodConfig("claude-sonnet-5-5", layout="split", contract_block=(level == "D4")))
            hashes.add(prefix_hash("claude-sonnet-5-5", params))
            part2.append(params["system"][4]["text"])
            assert r["inst"].auth in params["system"][4]["text"] and r["inst"].auth not in "".join(b["text"] for b in params["system"][:4])
    assert len(hashes) == 1 and len(set(part2)) == len(rendered)


@needs_cedar
def test_render_is_deterministic(tmp_path, rendered):
    r = rendered["s0000-plain"]
    again = bi.render(r["inst"], "plain", tmp_path / "again")
    assert again["sha256"] == r["record"]["sha256"]
    assert bi.lock_entry(again) == bi.lock_entry(r["record"])


def test_lock_file_pins_the_design_and_matches_the_rendered_sample(rendered):
    lock = json.loads(bi.LOCK.read_text())
    assert lock["seeds"] == bi.LOCK_SEEDS and lock["variants"] == list(bi.VARIANTS) and len(lock["instances"]) == 560
    assert lock["registry_sha256"] == registry.REGISTRY.sha256() and lock["intents_sha256"] == bi.sha(T02 / "intents.py")
    assert lock["names_sha256"] == bi.sha(T02 / "names.py") and lock["base_schema_sha256"] == bi.sha(bi.BASE_SCHEMA) and lock["wo_pin_sha256"] == bi.sha(bi.WO_PIN)
    for iid, r in rendered.items():
        assert lock["instances"][iid] == bi.lock_entry(r["record"]), iid
    assert all(e["auth"] != e["mirror"] for e in lock["instances"].values())


def test_generated_instances_are_not_committed():
    assert "t02_designated_source/instances/" in (ROOT / ".gitignore").read_text()
