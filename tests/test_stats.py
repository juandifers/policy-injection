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
