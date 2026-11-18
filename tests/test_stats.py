"""Exact one-sided Fisher test, checked against values computable by hand and published examples."""

from fractions import Fraction
from math import comb

import pytest

from pgi.analysis.stats import fisher_less


def test_tea_tasting():
    # Fisher's lady tasting tea: 3/4 vs 1/4 correct; P(X <= 1) = 17/70 (R: fisher.test(..., alternative) 0.2428571).
    assert fisher_less(3, 4, 1, 4) == pytest.approx(17 / 70)
    assert fisher_less(3, 4, 1, 4, exact=True) == Fraction(17, 70)


def test_dieting_example():
    # Wikipedia's dieting table: women 9/12 dieting, men 1/12. One-sided p = (C(10,0)C(14,12) + C(10,1)C(14,11)) / C(24,12).
    expected = Fraction(comb(10, 0) * comb(14, 12) + comb(10, 1) * comb(14, 11), comb(24, 12))
    assert expected == Fraction(3731, 2704156)
    assert fisher_less(9, 12, 1, 12, exact=True) == expected
    assert fisher_less(9, 12, 1, 12) == pytest.approx(0.0013797, abs=1e-7)


def test_baseline_shape():
    # 18/20 vs 0/20: only the observed table is as extreme: C(20,18) C(20,0) / C(40,18).
    assert fisher_less(18, 20, 0, 20, exact=True) == Fraction(comb(20, 18), comb(40, 18))


def test_no_change_or_increase_is_not_significant():
    assert fisher_less(18, 20, 18, 20) > 0.5
    assert fisher_less(0, 20, 5, 20) == 1.0
    assert fisher_less(20, 20, 20, 20) == 1.0       # degenerate margins: one table, p = 1


def test_rejects_impossible_counts():
    with pytest.raises(ValueError):
        fisher_less(5, 4, 0, 4)
    with pytest.raises(ValueError):
        fisher_less(1, 4, 0, 0)


# ---- two-sided Fisher (sum of hypergeometric probabilities no larger than the observed table's)
from pgi.analysis.stats import fisher_two_sided  # noqa: E402


def test_two_sided_tea_tasting():
    # P(X=3) = 16/70; tables at least as unlikely: X in {0, 1, 3, 4} -> (1 + 16 + 16 + 1) / 70 (R: 0.4857143).
    assert fisher_two_sided(3, 4, 1, 4, exact=True) == Fraction(34, 70)
    assert fisher_two_sided(3, 4, 1, 4) == pytest.approx(0.4857143, abs=1e-7)


def test_two_sided_extremes_and_symmetry():
    assert fisher_two_sided(4, 4, 0, 4, exact=True) == Fraction(2, 70)       # both corner tables
    assert fisher_two_sided(0, 4, 4, 4, exact=True) == Fraction(2, 70)       # direction does not matter
    assert fisher_two_sided(10, 20, 10, 20) == 1.0
    assert fisher_two_sided(9, 12, 1, 12) == pytest.approx(0.0027594, abs=1e-7)   # Wikipedia dieting table, two-sided
    with pytest.raises(ValueError):
        fisher_two_sided(1, 4, 0, 0)


# ---- Phase 2c: Holm step-down across a family of one-sided tests
from pgi.analysis.stats import holm  # noqa: E402


def test_holm_step_down_adjusts_and_stops_at_the_first_non_rejection():
    r = holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": 0.2}, alpha=0.05)
    assert [k for k in r] == ["a", "c", "b", "d"]                          # ascending by p
    assert r["a"] == {"p": 0.01, "adjusted": pytest.approx(0.04), "reject": True}
    assert r["c"]["adjusted"] == pytest.approx(0.09) and r["c"]["reject"] is False
    assert r["b"]["adjusted"] == pytest.approx(0.09) and r["b"]["reject"] is False   # monotone: never below the previous
    assert r["d"]["adjusted"] == pytest.approx(0.2) and r["d"]["reject"] is False


def test_holm_single_and_all_rejected():
    assert holm({"x": 0.03})["x"] == {"p": 0.03, "adjusted": 0.03, "reject": True}
    r = holm({"x": 1e-6, "y": 1e-3}, alpha=0.05)
    assert r["x"]["reject"] and r["y"]["reject"] and r["y"]["adjusted"] == pytest.approx(1e-3)
    assert holm({"x": 0.9})["x"]["adjusted"] == 0.9 and holm({"x": 0.6, "y": 0.7})["y"]["adjusted"] == 1.0
    with pytest.raises(ValueError):
        holm({})
