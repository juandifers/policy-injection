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


# ---- exact one-sided binomial bounds and exact McNemar (Phase 3 E1, 2026-11-22)
def _binom_cdf(k: int, n: int, p: Fraction | float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    p = float(p)
    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(0, k + 1))


def _bisect(f, lo: float, hi: float, tol: float = 1e-10) -> float:
    """Root of the monotone function f on [lo, hi] (f(lo) and f(hi) of opposite sign) by bisection."""
    flo = f(lo)
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = f(mid)
        if (fm < 0) == (flo < 0):
            lo, flo = mid, fm
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


def binomial_upper(k: int, n: int, alpha: float = 0.05) -> float:
    """Exact one-sided upper (1 - alpha) bound on a binomial proportion after k successes in n trials (Clopper-Pearson one
    tail): the p with P(X <= k | p) = alpha. 0/60 -> 0.0487; 0/120 -> 0.0247. k = n -> 1."""
    if not 0 <= k <= n or n <= 0 or not 0 < alpha < 1:
        raise ValueError(f"impossible counts {k}/{n} or alpha {alpha}")
    if k == n:
        return 1.0
    return _bisect(lambda p: _binom_cdf(k, n, p) - alpha, 0.0, 1.0)


def binomial_lower(k: int, n: int, alpha: float = 0.05) -> float:
    """Exact one-sided lower (1 - alpha) bound: the p with P(X >= k | p) = alpha. 6/60 -> 0.044. k = 0 -> 0."""
    if not 0 <= k <= n or n <= 0 or not 0 < alpha < 1:
        raise ValueError(f"impossible counts {k}/{n} or alpha {alpha}")
    if k == 0:
        return 0.0
    return _bisect(lambda p: (1 - _binom_cdf(k - 1, n, p)) - alpha, 0.0, 1.0)


def mcnemar_exact(b: int, c: int, exact: bool = False) -> float | Fraction:
    """Exact two-sided McNemar test on the discordant counts b (first condition only) and c (second only): twice the
    binomial tail at one half, capped at 1. 8 vs 0 -> 0.0078; 6 vs 0 -> 0.03125; no discordant pair -> 1."""
    if b < 0 or c < 0:
        raise ValueError(f"negative discordant counts {b}, {c}")
    n, k = b + c, min(b, c)
    if n == 0:
        return Fraction(1) if exact else 1.0
    tail = Fraction(sum(comb(n, i) for i in range(0, k + 1)), 2**n)
    p = min(Fraction(1), 2 * tail)
    return p if exact else float(p)
