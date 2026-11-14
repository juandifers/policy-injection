"""Clean-vs-mutated comparison: per-case allow counts, one-sided Fisher, detector counts, default mentions."""

import json
from pathlib import Path

import pytest

from pgi.analysis.stats import fisher_less
from pgi.runs.compare import comments_mentioning_default, compare, markdown

H = {"reference": "r1", "universe": "u1"}


def _run(tmp_path, name, counts, relying, comments=None, hashes=H, n=4):
    """A minimal run folder: config hashes, summary allow counts / default reliance, and policy files."""
    d = tmp_path / name
    summary = {}
    for gen, cc in counts.items():
        summary[f"s/{gen}"] = {"n": n, "valid": max(c["n"] for c in cc.values()),
                               "allow_counts": cc, "reference_allow_set": ["a"],
                               "default_reliance": {"samples_relying": relying[gen], "samples_checked": n,
                                                    "samples_by_field": {"t.f": relying[gen]} if relying[gen] else {}}}
        for i in range(n):
            p = d / "s" / gen / f"sample_{i:02d}" / "policy.cedar"
            p.parent.mkdir(parents=True)
            p.write_text((comments or {}).get((gen, i), "permit (principal, action, resource);\n"))
    (d / "summary.json").write_text(json.dumps(summary))
    (d / "config.json").write_text(json.dumps({"run_id": name, "scenarios": {"s": {"hashes": hashes}}}))
    return d


def test_compare_reports_both_counts_and_fisher_on_the_named_case(tmp_path):
    k = lambda k, n: {"k": k, "n": n}
    clean = _run(tmp_path, "clean", {"g": {"a": k(4, 4), "b": k(3, 4)}}, {"g": 3})
    probe = _run(tmp_path, "probe", {"g": {"a": k(4, 4), "b": k(0, 4)}}, {"g": 0})
    c = compare(clean, probe, fisher_cases=["b"])
    row = c["s"]["g"]
    assert row["cases"]["b"] == {"clean": "3/4", "probe": "0/4", "reference": "deny"}
    assert row["cases"]["a"] == {"clean": "4/4", "probe": "4/4", "reference": "allow"}
    assert row["fisher_less"]["b"] == pytest.approx(fisher_less(3, 4, 0, 4))
    assert row["default_reliance"] == {"clean": "3/4", "probe": "0/4", "clean_by_field": {"t.f": 3}, "probe_by_field": {}}


def test_fisher_is_none_without_valid_samples(tmp_path):
    k = lambda k, n: {"k": k, "n": n}
    clean = _run(tmp_path, "clean", {"g": {"b": k(0, 0)}}, {"g": 0})
    probe = _run(tmp_path, "probe", {"g": {"b": k(1, 4)}}, {"g": 0})
    assert compare(clean, probe, fisher_cases=["b"])["s"]["g"]["fisher_less"]["b"] is None


def test_compare_refuses_runs_scored_against_different_references(tmp_path):
    k = {"g": {"a": {"k": 1, "n": 1}}}
    clean = _run(tmp_path, "clean", k, {"g": 0})
    probe = _run(tmp_path, "probe", k, {"g": 0}, hashes={"reference": "r2", "universe": "u1"})
    with pytest.raises(ValueError, match="reference"):
        compare(clean, probe, fisher_cases=[])


def test_comments_mentioning_a_default_are_found_case_insensitively(tmp_path):
    k = {"g": {"a": {"k": 1, "n": 1}}}
    run = _run(tmp_path, "r", k, {"g": 0}, comments={
        ("g", 0): "// open_only defaults to true\npermit (principal, action, resource);\n",
        ("g", 2): "// Default: deny everything else\npermit (principal, action, resource);\n",
        ("g", 3): 'permit (principal, action, resource) when { context.default == 1 };\n'})  # not a comment
    found = comments_mentioning_default(run)
    assert found["s"]["g"]["samples"] == [0, 2]
    assert found["s"]["g"]["lines"][0] == {"sample": 0, "line": "// open_only defaults to true"}


def test_markdown_has_the_per_case_table(tmp_path):
    k = lambda k, n: {"k": k, "n": n}
    clean = _run(tmp_path, "clean", {"g": {"b": k(3, 4)}}, {"g": 3})
    probe = _run(tmp_path, "probe", {"g": {"b": k(0, 4)}}, {"g": 0})
    md = markdown(compare(clean, probe, fisher_cases=["b"]), "clean", "probe")
    assert "| b | deny | 3/4 | 0/4 |" in md and "Fisher" in md
