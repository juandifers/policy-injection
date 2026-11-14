"""Small exact statistics, stdlib only."""

from __future__ import annotations

from fractions import Fraction
from math import comb


def fisher_less(k1: int, n1: int, k2: int, n2: int, exact: bool = False) -> float | Fraction:
    """One-sided Fisher exact test that group 2's success rate is lower than group 1's.

    Table [[k1, n1-k1], [k2, n2-k2]] with both margins fixed; X = successes in group 2 is hypergeometric
    (N = n1+n2 draws, K = k1+k2 successes, n2 in group 2). Returns P(X <= k2).
    """
    if not (0 <= k1 <= n1 and 0 <= k2 <= n2 and n1 > 0 and n2 > 0):
        raise ValueError(f"impossible counts {k1}/{n1}, {k2}/{n2}")
    big_n, big_k = n1 + n2, k1 + k2
    lo = max(0, big_k - n1)
    p = Fraction(sum(comb(big_k, x) * comb(big_n - big_k, n2 - x) for x in range(lo, k2 + 1)), comb(big_n, n2))
    return p if exact else float(p)
