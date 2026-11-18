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


def fisher_two_sided(k1: int, n1: int, k2: int, n2: int, exact: bool = False) -> float | Fraction:
    """Two-sided Fisher exact test: the total probability of every table at most as likely as the observed one.

    Same hypergeometric setup as fisher_less (X = successes in group 2). This is R's `fisher.test` definition
    for 2x2 tables, not the doubled one-sided tail.
    """
    if not (0 <= k1 <= n1 and 0 <= k2 <= n2 and n1 > 0 and n2 > 0):
        raise ValueError(f"impossible counts {k1}/{n1}, {k2}/{n2}")
    big_n, big_k = n1 + n2, k1 + k2
    lo, hi = max(0, big_k - n1), min(big_k, n2)
    total = comb(big_n, n2)
    pmf = {x: Fraction(comb(big_k, x) * comb(big_n - big_k, n2 - x), total) for x in range(lo, hi + 1)}
    p = sum((q for q in pmf.values() if q <= pmf[k2]), Fraction(0))
    return p if exact else float(p)


def holm(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, dict]:
    """Holm step-down over a family of tests: sorted ascending, the i-th (1-based) p is compared with alpha/(m-i+1);
    rejection stops at the first failure. Returns, in ascending order, {name: {p, adjusted, reject}} where `adjusted` is
    the monotone Holm-adjusted p (min(1, (m-i+1) p), never below the previous one) and reject = adjusted <= alpha."""
    if not pvalues:
        raise ValueError("holm: empty family")
    items = sorted(pvalues.items(), key=lambda kv: (kv[1], kv[0]))
    m, running, rejecting, out = len(items), 0.0, True, {}
    for i, (name, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        reject = rejecting and running <= alpha
        rejecting = reject
        out[name] = {"p": p, "adjusted": running, "reject": reject}
    return out
