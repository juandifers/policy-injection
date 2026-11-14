"""Clean-run plumbing: replay reproduces records with zero API calls; blind spots and summaries are right."""

import dataclasses
import json
from pathlib import Path

import pytest

from pgi.generators import critic, naive
from pgi.generators.inputs import load_scenario_inputs
from pgi.llm.cache import CachedLLM
from pgi.oracle import sym
from pgi.runs.clean import run_naive, run_sondera, summarize, wilson
from pgi.runs.judge import score

DOMAIN = Path(__file__).resolve().parents[1] / "domains" / "assetopsbench"
S01 = DOMAIN / "scenarios" / "s01_close_after_approval"


@pytest.fixture(autouse=True, scope="module")
def _symcc():
    try:
        sym.check_available()
    except sym.SymccUnavailable as e:
        pytest.skip(str(e))


class Fake:
    """Generator returns the weak_same_wo policy; judge says NO MISMATCHES. Counts calls."""

    name = "fake"

    def __init__(self):
        self.calls = 0

    def call(self, model, messages, temperature, params):
        self.calls += 1
        judge = "policy reviewer" in params["system"][0]["text"]
        text = "NO MISMATCHES" if judge else "```cedar\n" + (S01 / "weak_same_wo.cedar").read_text() + "```"
        return {"model": f"{model}-v1", "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
                "usage": {"input_tokens": 100, "cache_read_input_tokens": 1000, "output_tokens": 50}}

    def text(self, raw):
        return raw["content"][0]["text"]

    def model_version(self, raw):
        return raw["model"]

    def usage(self, raw):
        return raw["usage"]


def strip_hits(rows, run_dir):
    """Records minus what legitimately differs between a run and its replay: cache_hit and the run folder path."""
    s = json.dumps(rows, sort_keys=True, default=str).replace(str(run_dir), "RUN")
    return s.replace('"cache_hit": true', '"cache_hit": X').replace('"cache_hit": false', '"cache_hit": X')


def test_replay_makes_zero_api_calls_and_reproduces_records(tmp_path):
    inp = load_scenario_inputs(S01)
    cache = tmp_path / "cache"
    first = Fake()
    llm = CachedLLM(first, cache)
    rows1 = [run_naive(llm, inp, naive.NaiveConfig("claude-haiku-5-5"), i, tmp_path / "a" / f"n{i}") for i in range(2)]
    rows1 += [run_sondera(llm, inp, critic.SonderaConfig("claude-haiku-5-5"), i, tmp_path / "a" / f"s{i}") for i in range(2)]
    assert first.calls > 0
    replay_provider = Fake()
    replay = CachedLLM(replay_provider, cache, allow_api=False)
    rows2 = [run_naive(replay, inp, naive.NaiveConfig("claude-haiku-5-5"), i, tmp_path / "b" / f"n{i}") for i in range(2)]
    rows2 += [run_sondera(replay, inp, critic.SonderaConfig("claude-haiku-5-5"), i, tmp_path / "b" / f"s{i}") for i in range(2)]
    assert replay_provider.calls == 0 and replay.api_calls == 0
    assert strip_hits(rows1, tmp_path / "a") == strip_hits(rows2, tmp_path / "b")
    assert (tmp_path / "a/n0/policy.cedar").read_text() == (tmp_path / "b/n0/policy.cedar").read_text()


def test_blind_spot_is_flagged_when_the_universe_lacks_the_witness(tmp_path):
    """weak_same_wo over a universe without c3: enumeration sees no surplus, symcc does -> blind spot on close."""
    lines = (S01 / "universe.yaml").read_text().splitlines()
    i = next(k for k, l in enumerate(lines) if l.strip().startswith("- id: c3"))
    j = next(k for k in range(i + 1, len(lines)) if lines[k].strip().startswith("- id:"))
    shrunk = tmp_path / "universe.yaml"
    shrunk.write_text("\n".join(lines[:i] + lines[j:]) + "\n")
    inp = load_scenario_inputs(S01)
    inp = dataclasses.replace(inp, folder=tmp_path)
    (tmp_path / "reference.cedar").write_text((S01 / "reference.cedar").read_text())
    r = score(S01 / "weak_same_wo.cedar", inp)
    assert r["enumeration"]["surplus"] == []
    assert r["symbolic"]["blind_spots"] == ['AOB::Action::"close_workorder"']
    assert r["symbolic"]["replay_failures"] == []


def test_invalid_policy_gets_no_oracle_result(tmp_path):
    p = tmp_path / "bad.cedar"
    p.write_text("I can't help with that.")
    r = score(p, load_scenario_inputs(S01))
    assert r == {"validation": r["validation"], "valid": False}


def test_wilson_interval():
    assert wilson(0, 0) is None
    lo, hi = wilson(10, 20)
    assert lo < 0.5 < hi and abs((lo + hi) / 2 - 0.5) < 1e-9
    assert wilson(20, 20)[1] == 1.0 and wilson(0, 20)[0] == 0.0


def test_summary_counts(tmp_path):
    inp = load_scenario_inputs(S01)
    llm = CachedLLM(Fake(), tmp_path / "cache")
    rows = [run_naive(llm, inp, naive.NaiveConfig("claude-haiku-5-5"), i, tmp_path / f"n{i}") for i in range(2)]
    s = summarize("claude-haiku-5-5", rows)
    assert s["n"] == 2 and s["valid"] == 2 and s["nonempty_surplus"] == 2 and s["nonempty_deficit"] == 0
    assert s["surplus_case_counts"] == {"c3": 2}
    assert s["clean_envelope"] == ["c2", "c3", "list_main"]
    assert s["model_versions"] == ["claude-haiku-5-5-v1"] and s["blind_spots"] == []


# ---- 2a: judge pass rates and judge flips on unchanged behaviour
from pgi.runs.judge import same_behaviour  # noqa: E402

REF_TEXT = (S01 / "reference.cedar").read_text()
WEAK_TEXT = (S01 / "weak_same_wo.cedar").read_text()


class Scripted(Fake):
    """Generations and judge replies from two queues (Fake's record format)."""

    def __init__(self, generations, judgements):
        super().__init__()
        self.generations, self.judgements = list(generations), list(judgements)

    def call(self, model, messages, temperature, params):
        self.calls += 1
        judge = "policy reviewer" in params["system"][0]["text"]
        text = self.judgements.pop(0) if judge else "```cedar\n" + self.generations.pop(0) + "```"
        return {"model": model, "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}


def write(tmp_path, name, text):
    (tmp_path / name).write_text(text)
    return tmp_path / name


def test_same_behaviour(tmp_path):
    inp = load_scenario_inputs(S01)
    ref = write(tmp_path, "a.cedar", REF_TEXT)
    commented = write(tmp_path, "b.cedar", "// only a comment differs\n" + REF_TEXT)
    weak = write(tmp_path, "c.cedar", WEAK_TEXT)
    bad = write(tmp_path, "d.cedar", "not cedar")
    assert same_behaviour(ref, commented, inp) is True
    assert same_behaviour(ref, weak, inp) is False
    assert same_behaviour(ref, bad, inp) is None  # an invalid round cannot be compared


def test_judge_flip_on_identical_behaviour_is_recorded(tmp_path):
    """Round 2 = round 1 plus a comment; the judge rejects then passes: one flip on unchanged behaviour."""
    prov = Scripted([REF_TEXT, "// note\n" + REF_TEXT], ["- something", "NO MISMATCHES"])
    row = run_sondera(CachedLLM(prov, tmp_path / "cache"), load_scenario_inputs(S01),
                      critic.SonderaConfig("claude-haiku-5-5"), 0, tmp_path / "s0")
    (pair,) = row["critic"]["round_pairs"]
    assert pair == {"rounds": [1, 2], "valid": [True, True], "same_text": False, "same_behaviour": True,
                    "judge": [False, True], "judge_changed": True}


def test_no_pair_when_judge_and_critic_pass_in_round_one(tmp_path):
    prov = Scripted([REF_TEXT], ["NO MISMATCHES"])
    row = run_sondera(CachedLLM(prov, tmp_path / "cache"), load_scenario_inputs(S01),
                      critic.SonderaConfig("claude-haiku-5-5"), 0, tmp_path / "s0")
    assert row["critic"]["round_pairs"] == [] and row["critic"]["passed"] and row["critic"]["rounds_used"] == 1


def _critic_row(passed, rounds_used, pairs=()):
    return {"sample": 0, "calls": [], "oracle": {"valid": False},
            "critic": {"passed": passed, "rounds_used": rounds_used, "round_pairs": list(pairs)}}


def _pair(same, changed):
    return {"rounds": [1, 2], "valid": [True, True], "same_text": False, "same_behaviour": same,
            "judge": [False, changed], "judge_changed": changed}


def test_summary_judge_pass_rates_and_noise_floor():
    rows = [_critic_row(True, 1),
            _critic_row(True, 2, [_pair(True, True)]),
            _critic_row(False, 3, [_pair(True, False), _pair(False, False)]),
            _critic_row(True, 3, [_pair(None, False), _pair(False, True)])]
    s = summarize("claude-haiku-5-5", rows)
    assert s["critic_passed"] == 3 and s["critic_pass_share"] == 0.75 and s["critic_pass_ci95"] == wilson(3, 4)
    assert s["critic_passed_round1"] == 1 and s["critic_passed_round1_share"] == 0.25
    assert s["rounds_to_pass_counts"] == {1: 1, 2: 1, 3: 1}       # passed samples only
    assert s["rounds_used_counts"] == {1: 1, 2: 1, 3: 2}          # unchanged: every sample
    # denominator: consecutive pairs with identical behaviour (same=None and same=False excluded)
    assert s["judge_flips_on_same_behaviour"] == {"flips": 1, "pairs": 2}


# ---- 2b: per-request allow counts
def _valid_row(allow):
    return {"sample": 0, "calls": [], "oracle": {"valid": True, "enumeration": {"allow_set": allow, "surplus": [], "deficit": []},
                                                 "symbolic": {"implies_reference": True, "per_action": [], "blind_spots": [], "replay_failures": []}}}


def test_summary_per_request_allow_counts():
    rows = [_valid_row(["a", "b"]), _valid_row(["a"]), _valid_row([]), {"sample": 3, "calls": [], "oracle": {"valid": False}}]
    s = summarize("claude-haiku-5-5", rows, case_ids=["a", "b", "c"], reference_allow=["a"])
    assert s["allow_counts"] == {"a": {"k": 2, "n": 3, "ci95": wilson(2, 3)},
                                 "b": {"k": 1, "n": 3, "ci95": wilson(1, 3)},
                                 "c": {"k": 0, "n": 3, "ci95": wilson(0, 3)}}   # n = valid samples
    assert s["reference_allow_set"] == ["a"]
    assert s["clean_envelope"] == ["a", "b"]  # union envelope unchanged


def test_markdown_has_one_case_table_per_scenario():
    from pgi.runs.clean import markdown
    rows = [_valid_row(["a"])]
    summ = {"s01/naive": summarize("claude-haiku-5-5", rows, case_ids=["a", "b"], reference_allow=["a"]),
            "s01/sondera": summarize("claude-haiku-5-5", rows, case_ids=["a", "b"], reference_allow=["a"])}
    md = markdown({"run_id": "r", "model": "m", "n": 1}, summ)
    assert "### s01: allow counts per request" in md
    assert "| case | P_ref | naive | sondera |" in md
    assert "| a | ✓ | 1/1 | 1/1 |" in md and "| b |  | 0/1 | 0/1 |" in md


# ---- 2c: literal provenance per sample and per scenario x generator
def test_each_sample_records_literal_provenance(tmp_path):
    """Fake returns weak_same_wo. Its APPR literal is stated by the trusted enum and by approve_workorder's free text."""
    inp = load_scenario_inputs(S01)
    row = run_naive(CachedLLM(Fake(), tmp_path / "cache"), inp, naive.NaiveConfig("claude-haiku-5-5"), 0, tmp_path / "n0")
    prov = {r["literal"]: r for r in row["provenance"]}
    assert json.loads((tmp_path / "n0" / "provenance.json").read_text()) == row["provenance"]
    appr = prov['PGI::ApprovalStatus::"APPR"']["sources"]
    assert "trusted_schema" in appr and "generated_schema" not in appr
    assert any("approve_workorder" in loc for loc in appr["manifest_free_text"])
    assert "intent" in prov['"MAIN"']["sources"]


def test_unparseable_policy_gets_a_provenance_error_not_a_crash(tmp_path):
    class Junk(Fake):
        def call(self, model, messages, temperature, params):
            return {**super().call(model, messages, temperature, params),
                    "content": [{"type": "text", "text": "I can't help with that."}]}
    row = run_naive(CachedLLM(Junk(), tmp_path / "cache"), load_scenario_inputs(S01),
                    naive.NaiveConfig("claude-haiku-5-5"), 0, tmp_path / "n0")
    assert "does not parse" in row["provenance"]["error"]


def test_summary_literal_provenance_counts_samples_not_occurrences():
    lit = lambda text, n, src: {"literal": text, "kind": "string", "role": "value", "occurrences": n, "sources": src}
    rows = [_valid_row([]) | {"provenance": [lit('"MAIN"', 3, {"intent": ["intent.md"]}), lit('"X"', 1, {})]},
            _valid_row([]) | {"provenance": [lit('"MAIN"', 1, {"intent": ["intent.md"]})]},
            {"sample": 2, "calls": [], "oracle": {"valid": False}, "provenance": {"error": "does not parse"}}]
    s = summarize("claude-haiku-5-5", rows)
    assert s["literal_provenance"] == {
        '"MAIN"': {"kind": "string", "role": "value", "samples": 2, "sources": {"intent": ["intent.md"]}},
        '"X"': {"kind": "string", "role": "value", "samples": 1, "sources": {}}}
    assert s["value_literals_without_trusted_source"] == ['"X"']
    assert s["provenance_parsed"] == 2


def test_value_literal_from_vendor_text_only_is_flagged_but_scope_names_are_not():
    row = lambda text, role, src: {"literal": text, "kind": "string", "role": role, "occurrences": 1, "sources": src}
    rows = [_valid_row([]) | {"provenance": [
        row('"APPROVED"', "value", {"manifest_free_text": ["wo:x.description"]}),
        row('"MAIN"', "value", {"intent": ["intent.md"], "manifest_free_text": ["wo:y.description"]}),
        row('AOB::Action::"x"', "scope", {"generated_schema": ["g"]})]}]
    assert summarize("m", rows)["value_literals_without_trusted_source"] == ['"APPROVED"']


def test_markdown_has_one_literal_table_per_scenario():
    from pgi.runs.clean import markdown
    lit = {"literal": '"MAIN"', "kind": "string", "role": "value", "occurrences": 1, "sources": {"intent": ["intent.md"], "manifest_other": ["x"]}}
    vend = {"literal": '"APPROVED"', "kind": "string", "role": "value", "occurrences": 1, "sources": {"manifest_free_text": ["d"]}}
    act = {"literal": 'AOB::Action::"x"', "kind": "entity", "role": "scope", "occurrences": 1, "sources": {"generated_schema": ["g"]}}
    rows = [_valid_row([]) | {"provenance": [lit, vend, act]}]
    summ = {"s01/naive": summarize("m", rows), "s01/sondera": summarize("m", rows + rows)}
    md = markdown({"run_id": "r", "model": "m", "n": 1}, summ)
    assert "### s01: value literals" in md and "### s01: scope names" in md
    assert md.index("### s01: value literals") < md.index("### s01: scope names")
    assert '| `"MAIN"` | 1/1 | 2/2 | yes | intent, manifest_other |' in md
    assert '| `"APPROVED"` | 1/1 | 2/2 | **no** | manifest_free_text |' in md
    assert '| `AOB::Action::"x"` | 1/1 | 2/2 | generated_schema |' in md


# ---- 2d: cause tags per sample and per scenario x generator
def test_each_sample_records_cause_tags(tmp_path):
    """Fake returns weak_same_wo: surplus c3, explained by the reference's wonum conjunct."""
    row = run_naive(CachedLLM(Fake(), tmp_path / "cache"), load_scenario_inputs(S01),
                    naive.NaiveConfig("claude-haiku-5-5"), 0, tmp_path / "n0")
    tags = row["cause_tags"]
    assert list(tags["surplus"]) == ["c3"] and tags["deficit"] == {}
    assert tags["surplus"]["c3"]["tag"] == ["close-after-approval: context.approval.wonum == context.input.wonum"]
    assert json.loads((tmp_path / "n0" / "oracle.json").read_text())["cause_tags"] == tags


def test_summary_counts_cause_tags_per_case():
    ex = lambda tag: {"tag": tag}
    rows = [_valid_row([]) | {"cause_tags": {"surplus": {}, "deficit": {"d1": ex(["p: x == 1"]), "d2": ex("action not granted")}}},
            _valid_row([]) | {"cause_tags": {"surplus": {}, "deficit": {"d1": ex(["p: x == 1"])}}},
            _valid_row([]) | {"cause_tags": {"surplus": {"s1": ex(["r: y"])}, "deficit": {}}}]
    s = summarize("m", rows)
    assert s["cause_tag_counts"] == {"surplus": {"s1": {"r: y": 1}},
                                     "deficit": {"d1": {"p: x == 1": 2}, "d2": {"action not granted": 1}}}


def test_markdown_lists_cause_tags_per_scenario():
    from pgi.runs.clean import markdown
    rows = [_valid_row([]) | {"cause_tags": {"surplus": {}, "deficit": {"d1": {"tag": ["p: x == 1"]}}}}]
    md = markdown({"run_id": "r", "model": "m", "n": 1}, {"s01/naive": summarize("m", rows)})
    assert "### s01: cause tags" in md and "| deficit | d1 | naive | `p: x == 1` | 1 |" in md


# ---- default reliance per sample and per scenario x generator
def test_each_sample_records_default_reliance(tmp_path):
    """weak_same_wo allows list_main, which sets the defaulted site_id; omitting it is denied."""
    row = run_naive(CachedLLM(Fake(), tmp_path / "cache"), load_scenario_inputs(S01),
                    naive.NaiveConfig("claude-haiku-5-5"), 0, tmp_path / "n0")
    rows = row["default_reliance"]
    assert [(r["case"], r["field"], r["verdict"]) for r in rows] == [("list_main", "site_id", "omission_denied")]
    assert json.loads((tmp_path / "n0" / "defaults.json").read_text()) == rows


def test_summary_counts_samples_relying_on_a_default():
    rel = lambda *fields: [{"tool": "t", "field": f, "verdict": v} for f, v in fields]
    rows = [_valid_row([]) | {"default_reliance": rel(("a", "relies"), ("b", "relies"))},
            _valid_row([]) | {"default_reliance": rel(("a", "relies"), ("c", "untestable"))},
            _valid_row([]) | {"default_reliance": rel(("a", "omission_denied"))},
            _valid_row([]) | {"default_reliance": None}]  # invalid samples record None
    d = summarize("m", rows)["default_reliance"]
    assert (d["samples_relying"], d["samples_checked"]) == (2, 3)
    assert d["samples_by_field"] == {"t.a": 2, "t.b": 1}
    assert d["verdicts"] == {"omission_denied": 1, "relies": 3, "untestable": 1}


def test_markdown_lists_default_reliance():
    from pgi.runs.clean import markdown
    rows = [_valid_row([]) | {"default_reliance": [{"tool": "t", "field": "a", "verdict": "relies"}]}]
    md = markdown({"run_id": "r", "model": "m", "n": 1}, {"s01/naive": summarize("m", rows)})
    assert "## Default reliance" in md and "| s01 | naive | 1/1 | t.a: 1 |" in md


# ---- atomic run folders
from pgi.runs.clean import atomic_run_dir  # noqa: E402


def test_successful_run_is_renamed_into_place(tmp_path):
    with atomic_run_dir(tmp_path, "r1") as d:
        assert d == tmp_path / ".tmp-r1"
        (d / "x.json").write_text("{}")
    assert (tmp_path / "r1" / "x.json").is_file() and not (tmp_path / ".tmp-r1").exists()
    assert not (tmp_path / "r1" / "FAILED").exists()


def test_injected_failure_leaves_tmp_folder_with_traceback_and_no_final_folder(tmp_path):
    inp = load_scenario_inputs(S01)

    class Boom(Fake):
        def call(self, *a, **k):
            raise RuntimeError("injected failure")

    with pytest.raises(RuntimeError, match="injected failure"):
        with atomic_run_dir(tmp_path, "r2") as d:
            run_naive(CachedLLM(Fake(), tmp_path / "cache"), inp, naive.NaiveConfig("claude-haiku-5-5"), 0, d / "s" / "n0")
            run_naive(CachedLLM(Boom(), tmp_path / "cache2"), inp, naive.NaiveConfig("claude-haiku-5-5"), 1, d / "s" / "n1")
    assert not (tmp_path / "r2").exists()
    failed = (tmp_path / ".tmp-r2" / "FAILED").read_text()
    assert "RuntimeError: injected failure" in failed and "Traceback" in failed
    assert (tmp_path / ".tmp-r2" / "s" / "n0" / "oracle.json").is_file()  # partial work kept for inspection


def test_atomic_run_dir_refuses_an_existing_run(tmp_path):
    (tmp_path / "r3").mkdir()
    with pytest.raises(FileExistsError):
        with atomic_run_dir(tmp_path, "r3"):
            pass


def test_paths_inside_the_run_folder_are_recorded_relative_to_it(tmp_path):
    from pgi.runs import clean
    inp = load_scenario_inputs(S01)
    with atomic_run_dir(tmp_path, "r4") as d:
        run_naive(CachedLLM(Fake(), tmp_path / "cache"), inp, naive.NaiveConfig("claude-haiku-5-5"), 0, d / "s" / "n0")
    text = (tmp_path / "r4" / "s" / "n0" / "oracle.json").read_text()
    assert ".tmp-r4" not in text and str(tmp_path) not in text
    assert json.loads(text)["validation"]["policy"] == "s/n0/policy.cedar"
    assert clean._RUN_DIR is None  # reset after the run
