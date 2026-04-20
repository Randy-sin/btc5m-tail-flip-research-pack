from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class CalibrationBucket:
    key: str
    observations: int
    trades: int
    wins: int
    win_rate: float
    wilson_low: float
    wilson_high: float
    break_even: float
    edge_abs: float
    posterior_prob_edge_positive: float


def wilson_interval(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def _betacf(a: float, b: float, x: float, max_iter: int = 200, eps: float = 3e-12) -> float:
    # Continued fraction for incomplete beta, Numerical Recipes style.
    fpmin = 1e-300
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def beta_cdf(x: float, a: float, b: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def posterior_prob_edge_positive(wins: int, losses: int, break_even: float, alpha0: float = 1.0, beta0: float = 1.0) -> float:
    a = alpha0 + wins
    b = beta0 + losses
    return 1.0 - beta_cdf(break_even, a, b)


def price_bucket(price: float) -> str:
    cents = round(price * 100)
    return f"{cents}c"


def assign_deciles(values: List[float]) -> List[int]:
    if not values:
        return []
    order = sorted(range(len(values)), key=lambda i: values[i])
    dec = [0] * len(values)
    n = len(values)
    for rank, idx in enumerate(order):
        dec[idx] = min(9, int(rank * 10 / max(n, 1)))
    return dec


def aggregate_calibration(rows: List[Dict[str, object]], group_field: str = "price_b_decile") -> List[CalibrationBucket]:
    groups: Dict[str, List[Dict[str, object]]] = {}
    for r in rows:
        groups.setdefault(str(r[group_field]), []).append(r)
    out: List[CalibrationBucket] = []
    for key, rs in sorted(groups.items(), key=lambda kv: kv[0]):
        obs_n = len(rs)
        trade_rs = [r for r in rs if bool(r.get("trade", True))]
        n = len(trade_rs)
        wins = sum(1 for r in trade_rs if str(r.get("result_win", "False")).lower() in {"true", "1", "yes"})
        be = sum(float(r.get("break_even", r.get("token_price", 0.0))) for r in trade_rs) / n if n else 0.0
        rate = wins / n if n else 0.0
        lo, hi = wilson_interval(wins, n) if n else (0.0, 1.0)
        post = posterior_prob_edge_positive(wins, max(0, n - wins), be) if n else 0.0
        out.append(CalibrationBucket(
            key=key,
            observations=obs_n,
            trades=n,
            wins=wins,
            win_rate=rate,
            wilson_low=lo,
            wilson_high=hi,
            break_even=be,
            edge_abs=rate - be,
            posterior_prob_edge_positive=post,
        ))
    return out


def write_buckets_csv(buckets: Iterable[CalibrationBucket], path: str) -> None:
    fields = ["key", "observations", "trades", "wins", "win_rate", "wilson_low", "wilson_high", "break_even", "edge_abs", "posterior_prob_edge_positive"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for b in buckets:
            writer.writerow({name: getattr(b, name) for name in fields})
