"""Split prompt layout (Phase 3, 2026-11-20): one cached prefix shared by every instance, cell and repair round of t02.

Blocks 1-4 (instructions, language reference v2, event schema, the MaintData-only action schema = part 1) must be
byte-identical for all seeds, variants and cells and carry the only cache breakpoint (block 4); everything that varies
(part 2 = the instance's own declarations, the D4 contract block, the intent) sits after it. The validator and the oracle
keep using the full schema; only the prompt shows it in two parts. The default layout and its recorded byte identity
(tests/test_dogwood_generator.py) are untouched.

The instances are the t02 builder's (build_instances.py: the lock-file seeds, its manifests, intents and catalogue); the
sweep uses the generated (unlinked) schemas for speed, the cedar-marked tests the session-linked ones.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import shutil
import sys
from pathlib import Path

import pytest
import yaml

from pgi.generators.dogwood import (FINAL_LINE, INSTRUCTIONS_SCHEMA_ONLY, LANGUAGE_REFERENCE, LANGUAGE_REFERENCE_V2, LAYOUTS,
                                    NaiveDogwoodConfig, SonderaDogwoodConfig, build_request, judge_request, regeneration_request,
                                    static_blocks, static_blocks_split)
from pgi.generators.dogwood_inputs import DogwoodInputs, load_dogwood_inputs, load_snapshot, snapshot
from pgi.generators.schema_split import SchemaSplitError, declarations, split_schema
from pgi.llm.cache import cache_key, key_hash
from pgi.llm.prefix import prefix_blocks, prefix_hash
from pgi.schemagen import generate_dogwood, link_session_id

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domains" / "assetopsbench"
T01 = DOMAIN / "scenarios" / "t01_close_after_approval"
T02 = DOMAIN / "scenarios" / "t02_designated_source"
WO_PIN = DOMAIN / "manifests" / "wo.tools.json"
EVENTS = DOMAIN / "schema" / "agentcore.dwschema"
RUNS = ROOT / "runs"
sys.path.insert(0, str(T02))
from names import MAINT_TARGET, POOL  # noqa: E402

needs_cedar = pytest.mark.skipif(shutil.which("cedar") is None, reason="cedar CLI not on PATH")
import build_instances as bi  # noqa: E402  (the t02 builder: instances, manifests, intents, catalogue)

SEEDS, VARIANTS = bi.LOCK_SEEDS, bi.VARIANTS
GOAL_LEVEL = (T01 / "intent.goal-level.md").read_text()


# ---- t02 instances through the builder (generated, unlinked schemas for the sweep; linked ones in the cedar-marked tests)
def full_schema(d: Path, inst: bi.Instance, variant: str) -> str:
    return bi.generated_schema(inst, variant, d)[0]


def intents(inst: bi.Instance) -> dict[str, str]:
    return bi.intent_texts(inst)


def catalogue_file(d: Path, inst: bi.Instance) -> Path:
    p = d / "admission.catalogue.yaml"
    p.write_text(yaml.safe_dump(bi.catalogue(inst)))
    return p


def approval_tool(name: str, decisions, kinds) -> dict:
    return bi.approval_tool(name, decisions, kinds)


def make_inputs(d: Path, schema_text: str, base_text: str, intent_text: str, intent_name: str, catalogue: Path | None,
                servers=("MaintData", "auth", "mirror")) -> DogwoodInputs:
    (d / "schema.cedarschema").write_text(schema_text)
    (d / "base.cedarschema").write_text(base_text)
    (d / "intent.md").write_text(intent_text)
    return DogwoodInputs("t02_synthetic", d, d / "schema.cedarschema", schema_text, EVENTS, EVENTS.read_text(), tuple(servers),
                         tuple(d / f"{s}.tools.json" for s in servers), intent_name, d / "intent.md", intent_text,
                         d / "gold.dw", d / "traces.yaml", None, {}, "base", catalogue, d / "base.cedarschema", base_text)


@pytest.fixture(scope="module")
def base_generated() -> str:
    return bi.BASE_GENERATED.read_text()   # committed MaintData-only schema (prompt part 1), pinned by tests/test_t02_instances.py


@pytest.fixture(scope="module")
def sample(tmp_path_factory, base_generated) -> dict:
    """One rendered plain-variant instance (seed 0) with generated (unlinked) schemas."""
    d = tmp_path_factory.mktemp("sample")
    inst = bi.instance(0)
    full = full_schema(d, inst, "plain")
    return {"inst": inst, "full": full, "base": base_generated, "dir": d, "catalogue": catalogue_file(d, inst)}


# ---- schemagen: target prefixing
def test_generate_dogwood_default_is_unchanged_and_targets_prefix_tool_names(base_generated):
    pinned = (T01 / "schema" / "t01.dogwood.generated.cedarschema").read_text()
    assert generate_dogwood([T01 / "manifests" / "wo.maintenance-data.tools.json", T01 / "manifests" / "authority.tools.json"]) == pinned
    assert f'action "{MAINT_TARGET}___close_workorder"' in base_generated and 'action "close_workorder"' not in base_generated
    assert f"type {MAINT_TARGET}___close_workorderInput" in base_generated
    assert json.loads(WO_PIN.read_text())["tools"][0]["name"] == "list_workorders"   # manifests on disk keep unprefixed names


def test_targets_must_name_given_manifests_and_collisions_are_refused(tmp_path):
    with pytest.raises(Exception, match="targets"):
        generate_dogwood([WO_PIN], targets={tmp_path / "other.json": "X"})
    a = tmp_path / "a.json"
    a.write_text(json.dumps({"tools": [approval_tool("get_approval", *bi.VOCABULARIES[0])]}))
    b = tmp_path / "b.json"
    b.write_text(a.read_text())
    with pytest.raises(Exception, match="collide"):
        generate_dogwood([a, b], targets={a: "Same", b: "Same"})
    assert 'action "Same___get_approval"' in generate_dogwood([a, b], targets={a: "Same", b: "Other"})


# ---- schema split
def test_declarations_split_on_top_level_semicolons_and_roundtrip(sample):
    ns, full = declarations(sample["full"])
    ns_b, base = declarations(sample["base"])
    assert ns == ns_b == "Drupe"
    assert len(base) == 122 and len(full) == 130
    assert all(d.endswith(";") for d in full) and len(set(full)) == len(full)
    assert set(base) <= set(full)
    rebuilt = f"namespace {ns} {{\n" + "\n".join("  " + d for d in full) + "\n}\n"
    assert declarations(rebuilt) == (ns, full)


def test_split_schema_is_exact_and_wrapped_in_the_namespace(sample):
    part2 = split_schema(sample["full"], sample["base"])
    ns, decls = declarations(part2)
    assert ns == "Drupe" and len(decls) == 8
    auth, mirror = sample["inst"].auth, sample["inst"].mirror
    assert {d.split()[1].rstrip(";") for d in decls if d.startswith(("type", "entity"))} == {
        f"{auth}___get_approvalInput", f"{auth}___get_approvalOutput", f"{mirror}___get_approvalInput", f"{mirror}___get_approvalOutput",
        "approver_kind", "decision"}
    assert set(declarations(sample["base"])[1]) | set(decls) == set(declarations(sample["full"])[1])
    assert MAINT_TARGET not in part2
    # the full text is reproduced exactly by base + part 2 (same formatting), so nothing is paraphrased
    _, full_decls = declarations(sample["full"])
    assert [d for d in full_decls if d not in set(declarations(sample["base"])[1])] == decls


def test_split_schema_failure_modes(sample):
    full, base = sample["full"], sample["base"]
    altered = base.replace(f"type {MAINT_TARGET}___close_workorderInput = {{", f"type {MAINT_TARGET}___close_workorderInput = {{\n    extra: String,", 1)
    assert altered != base
    with pytest.raises(SchemaSplitError, match="close_workorderInput"):
        split_schema(full, altered)
    with pytest.raises(SchemaSplitError, match="namespace"):
        split_schema(full, base.replace("namespace Drupe", "namespace Other", 1))
    with pytest.raises(SchemaSplitError, match="no declaration"):
        split_schema(full, full)
    with pytest.raises(SchemaSplitError):
        declarations("not a schema")


@needs_cedar
def test_split_holds_on_linked_schemas(tmp_path, sample):
    """The session link runs both texts through Cedar's translator; the MaintData declarations must survive it unchanged."""
    gen, base_gen = tmp_path / "full.generated.cedarschema", tmp_path / "base.generated.cedarschema"
    gen.write_text(sample["full"])
    base_gen.write_text(sample["base"])
    full, base = link_session_id(gen), link_session_id(base_gen)
    part2 = split_schema(full, base)
    assert len(declarations(part2)[1]) == 8 and "sessionId" in part2
    assert len(declarations(base)[1]) == 122


# ---- the split layout
def test_split_layout_blocks(sample):
    inst, d = sample["inst"], sample["dir"]
    inp = make_inputs(d, sample["full"], sample["base"], GOAL_LEVEL, "D0", sample["catalogue"])
    blocks = static_blocks_split(inp, NaiveDogwoodConfig("m", layout="split"))
    assert len(blocks) == 5
    assert blocks[0]["text"].startswith(INSTRUCTIONS_SCHEMA_ONLY) and "two parts" in blocks[0]["text"] and "one namespace" in blocks[0]["text"]
    assert blocks[1]["text"] == LANGUAGE_REFERENCE_V2 and LANGUAGE_REFERENCE_V2.startswith(LANGUAGE_REFERENCE)
    assert "<Target>___<tool>" in LANGUAGE_REFERENCE_V2 and "gateway administrator" in LANGUAGE_REFERENCE_V2 and "___" not in LANGUAGE_REFERENCE.split("InsuranceAPI")[0]
    assert blocks[2]["text"].startswith("## Temporal event schema") and EVENTS.read_text() in blocks[2]["text"]
    assert blocks[3]["text"].startswith("## Action schema, part 1") and sample["base"] in blocks[3]["text"]
    assert blocks[4]["text"].startswith("## Action schema, part 2") and split_schema(sample["full"], sample["base"]) in blocks[4]["text"]
    assert [i for i, b in enumerate(blocks) if "cache_control" in b] == [3] and blocks[3]["cache_control"] == {"type": "ephemeral"}
    assert inst.auth not in "".join(b["text"] for b in blocks[:4]) and inst.auth in blocks[4]["text"]
    # D4: the contract block is sixth, after the breakpoint
    six = static_blocks_split(inp, NaiveDogwoodConfig("m", layout="split", contract_block=True))
    assert six[:5] == blocks and len(six) == 6 and "cache_control" not in six[5]
    assert six[5]["text"].startswith("## Evidence-authority contract") and f"{inst.auth}___get_approval" in six[5]["text"]
    assert f"{MAINT_TARGET}___close_workorder" in six[5]["text"] and inst.decisions[0] in six[5]["text"]


def test_layout_and_contract_block_validation(sample):
    inp = make_inputs(sample["dir"], sample["full"], sample["base"], GOAL_LEVEL, "D0", None)
    assert LAYOUTS == ("default", "split")
    with pytest.raises(ValueError, match="layout"):
        build_request(inp, NaiveDogwoodConfig("m", layout="bogus"))
    with pytest.raises(ValueError, match="contract_block"):
        build_request(inp, NaiveDogwoodConfig("m", layout="default", contract_block=True))
    with pytest.raises(ValueError, match="catalogue"):
        build_request(inp, NaiveDogwoodConfig("m", layout="split", contract_block=True))
    no_base = DogwoodInputs(**{**inp.__dict__, "schema_base_path": None, "schema_base_text": None})
    with pytest.raises(ValueError, match="prompt_schema_base"):
        build_request(no_base, NaiveDogwoodConfig("m", layout="split"))
    with pytest.raises(ValueError, match="layout"):
        static_blocks(inp, True, layout="split")   # the default builder never renders the split layout


def test_default_layout_is_untouched_by_the_new_fields():
    inp = load_dogwood_inputs(T01, intent="goal-level", arm="L1")
    m0, p0 = build_request(inp, NaiveDogwoodConfig("claude-sonnet-5-5"))
    m1, p1 = build_request(inp, NaiveDogwoodConfig("claude-sonnet-5-5", layout="default", contract_block=False))
    assert (m0, p0) == (m1, p1)
    run = RUNS / "20261118T182621Z-temporal-clean-t01-goal-level-L1"
    assert p0["system"] == json.loads((run / "t01_close_after_approval" / "prompt_static.json").read_text())
    assert NaiveDogwoodConfig("m").as_dict()["layout"] == "default" and NaiveDogwoodConfig("m").as_dict()["contract_block"] is False
    s = SonderaDogwoodConfig("m", layout="split", contract_block=True)
    assert (s.naive().layout, s.naive().contract_block) == ("split", True)
    assert inp.schema_base_path is None and inp.schema_base_text is None   # t01 declares no prompt_schema_base


def test_build_regeneration_and_judge_requests_under_the_split_layout(sample):
    inp = make_inputs(sample["dir"], sample["full"], sample["base"], GOAL_LEVEL, "D0", sample["catalogue"])
    cfg = SonderaDogwoodConfig("m", layout="split")
    messages, params = build_request(inp, cfg.naive())
    assert messages == [{"role": "user", "content": f"{GOAL_LEVEL.rstrip()}\n\n{FINAL_LINE}"}]
    assert params["thinking"] == {"type": "adaptive"} and params["output_config"] == {"effort": "high"}
    from pgi.generators.dogwood import DogwoodCritique
    from pgi.oracle.temporal import TemporalValidationReport
    det = DogwoodCritique(False, TemporalValidationReport("p", "s", False, ("boom",), ()), ("invalid: boom",))
    rm, rp = regeneration_request(inp, cfg, "permit (principal, action, resource);", det, "- mismatch")
    assert rp["system"][:4] == params["system"][:4] and rp["system"][4:] == params["system"][4:]
    assert [i for i, b in enumerate(rp["system"]) if "cache_control" in b] == [3]
    assert "Your previous attempt" in rm[0]["content"] and rm[0]["content"].endswith(FINAL_LINE)
    assert prefix_hash("m", rp) == prefix_hash("m", params)
    jm, jp = judge_request(inp, "permit (principal, action, resource);", cfg)
    assert jp["system"][1]["text"].startswith(LANGUAGE_REFERENCE_V2) and "cache_control" in jp["system"][-1]
    assert "## Action schema" not in "".join(b["text"] for b in jp["system"])   # the judge sees no action schema, as before
    jm0, jp0 = judge_request(load_dogwood_inputs(T01, intent="goal-level"), "x", SonderaDogwoodConfig("m"))
    assert jp0["system"][1]["text"].startswith(LANGUAGE_REFERENCE) and not jp0["system"][1]["text"].startswith(LANGUAGE_REFERENCE_V2)


# ---- prefix identity
def test_prefix_blocks_and_hash():
    inp = load_dogwood_inputs(T01, intent="goal-level")
    _, params = build_request(inp, NaiveDogwoodConfig("m"))
    assert prefix_blocks(params) == params["system"]            # default layout: the breakpoint is the last block
    h = prefix_hash("m", params)
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert prefix_hash("m", {**params, "max_tokens": 1}) == h   # max_tokens is not part of the prompt prefix
    assert prefix_hash("other", params) != h
    assert prefix_hash("m", {**params, "output_config": {"effort": "low"}}) != h
    assert prefix_hash("m", {**params, "thinking": {"type": "disabled"}}) != h
    _, jp = judge_request(inp, "x", SonderaDogwoodConfig("m"))
    assert prefix_hash("m", jp) != h
    with pytest.raises(ValueError, match="cache_control"):
        prefix_hash("m", {"system": [{"type": "text", "text": "a"}]})


def test_blocks_1_to_4_and_the_prefix_hash_are_identical_over_all_seeds_variants_and_cells(tmp_path, base_generated):
    """The guard: 140 seeds x 4 variants x 5 cells; the only cache_control is on block 4; nothing instance-specific before it."""
    prefixes, hashes, part2_sizes = set(), set(), []
    pool_re = re.compile(r"\b(" + "|".join(POOL) + r")\b")
    stamp_re = re.compile(r"\d{8}T\d{6}Z")
    for seed in SEEDS:
        inst = bi.instance(seed)
        d = tmp_path / f"s{seed}"
        d.mkdir()
        for variant in VARIANTS:
            full = full_schema(d, inst, variant)
            cat = catalogue_file(d, inst)
            for cell, text in intents(inst).items():
                inp = make_inputs(d, full, base_generated, text, cell, cat)
                cfg = NaiveDogwoodConfig("claude-sonnet-5-5", layout="split", contract_block=(cell == "D4"))
                messages, params = build_request(inp, cfg)
                system = params["system"]
                assert [i for i, b in enumerate(system) if "cache_control" in b] == [3]
                head = json.dumps(system[:4], sort_keys=True)
                prefixes.add(head)
                hashes.add(prefix_hash("claude-sonnet-5-5", params))
                assert prefix_blocks(params) == system[:4]
                assert not pool_re.search(head) and not stamp_re.search(head) and f"seed {seed}" not in head and f"phase3-e1:{seed}" not in head
                tail = "".join(b["text"] for b in system[4:]) + messages[0]["content"]
                assert inst.auth in tail and inst.mirror in system[4]["text"]
                assert len(system) == (6 if cell == "D4" else 5)
                part2_sizes.append(len(system[4]["text"]))
    assert len(prefixes) == 1 and len(hashes) == 1
    assert max(part2_sizes) < 2500   # part 2 stays small: the only uncached schema text


# ---- dogwood_inputs: prompt_schema_base
def _scenario_copy(tmp_path: Path) -> Path:
    """A copy of the t01 base scenario (no arms) inside a copy of the domain folder, so relative paths keep working."""
    dom = tmp_path / "assetopsbench"
    (dom / "schema").mkdir(parents=True)
    shutil.copyfile(EVENTS, dom / "schema" / EVENTS.name)
    dst = dom / "scenarios" / T01.name
    shutil.copytree(T01, dst, ignore=shutil.ignore_patterns("arms", "__pycache__", "variants"))
    return dst


def test_prompt_schema_base_is_loaded_hashed_snapshotted_and_optional(tmp_path, base_generated):
    sc = _scenario_copy(tmp_path)
    (sc / "schema" / "base.cedarschema").write_text(base_generated)
    meta = yaml.safe_load((sc / "scenario.yaml").read_text())
    meta["prompt_schema_base"] = f"scenarios/{sc.name}/schema/base.cedarschema"
    (sc / "scenario.yaml").write_text(yaml.safe_dump(meta, sort_keys=False))
    inp = load_dogwood_inputs(sc)
    assert inp.schema_base_path == sc / "schema" / "base.cedarschema" and inp.schema_base_text == base_generated
    assert inp.hashes["schema_base"] == hashlib.sha256(base_generated.encode()).hexdigest()
    snap = snapshot(inp, tmp_path / "snap")
    assert snap.schema_base_text == base_generated and (tmp_path / "snap" / "schema_base" / "base.cedarschema").is_file()
    assert load_snapshot(tmp_path / "snap").hashes == inp.hashes
    # an arm may override it
    meta["arms"] = {"X": {"prompt_schema_base": f"scenarios/{sc.name}/schema/base2.cedarschema"}}
    (sc / "schema" / "base2.cedarschema").write_text(base_generated + "\n")
    (sc / "scenario.yaml").write_text(yaml.safe_dump(meta, sort_keys=False))
    assert load_dogwood_inputs(sc, arm="X").schema_base_text == base_generated + "\n"
    # without the key: None, no hash entry, snapshot layout as before
    plain = load_dogwood_inputs(T01)
    assert plain.schema_base_path is None and "schema_base" not in plain.hashes


def test_split_layout_cache_key_differs_only_after_the_breakpoint(sample):
    """Two cells of one instance: same prefix hash, different cache keys (the intent is in the user turn)."""
    inp0 = make_inputs(sample["dir"], sample["full"], sample["base"], GOAL_LEVEL, "D0", sample["catalogue"])
    inp1 = make_inputs(sample["dir"], sample["full"], sample["base"], GOAL_LEVEL + "\nMore.\n", "D1", sample["catalogue"])
    cfg = NaiveDogwoodConfig("m", layout="split")
    (m0, p0), (m1, p1) = build_request(inp0, cfg), build_request(inp1, cfg)
    assert prefix_hash("m", p0) == prefix_hash("m", p1)
    assert key_hash(cache_key("m", m0, None, 0, p0)) != key_hash(cache_key("m", m1, None, 0, p1))
