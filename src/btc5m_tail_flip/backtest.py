from __future__ import annotations

import csv
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .core import Observation, TailFlipStrategy, StrategyConfig, break_even_cost
from .calibration import assign_deciles, price_bucket, aggregate_calibration


@dataclass(frozen=True)
class TradeEvent:
    ts: int
    price: float
    size: float
    side: str = "SELL"  # taker side relative to token; maker buy fills against taker sell


@dataclass(frozen=True)
class MakerFillResult:
    filled: float
    remaining_self: float
    filled_ts: Optional[int]
    fill_fraction: float


def simulate_maker_buy_fill(
    order_ts: int,
    limit_price: float,
    size: float,
    queue_ahead: float,
    trades_after: Iterable[TradeEvent],
) -> MakerFillResult:
    """Queue-aware maker buy fill simulation.

    For a maker BUY at 1c/2c, fills require later taker SELL volume at or below
    the limit. Existing bid size at that price must be consumed before us.
    """
    rem_queue = max(0.0, queue_ahead)
    rem_self = max(0.0, size)
    filled = 0.0
    filled_ts: Optional[int] = None
    for tr in sorted(trades_after, key=lambda x: x.ts):
        if tr.ts <= order_ts:
            continue
        if tr.price > limit_price:
            continue
        if tr.side.upper() not in {"SELL", "TAKER_SELL", "S"}:
            continue
        vol = max(0.0, tr.size)
        if rem_queue > 0:
            consume = min(rem_queue, vol)
            rem_queue -= consume
            vol -= consume
        if vol > 0 and rem_self > 0:
            take = min(rem_self, vol)
            rem_self -= take
            filled += take
            filled_ts = tr.ts
        if rem_self <= 1e-12:
            break
    return MakerFillResult(filled=filled, remaining_self=rem_self, filled_ts=filled_ts, fill_fraction=filled / size if size else 0.0)


def read_observations_csv(path: str) -> List[Observation]:
    out: List[Observation] = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            def fl(name: str, default: float = 0.0) -> float:
                val = r.get(name, "")
                return default if val in {"", None} else float(val)
            def optfl(name: str) -> Optional[float]:
                val = r.get(name, "")
                return None if val in {"", None} else float(val)
            out.append(Observation(
                market_id=r["market_id"],
                ts=int(r["ts"]),
                window_start_ts=int(r["window_start_ts"]),
                window_end_ts=int(r["window_end_ts"]),
                side=r["side"],
                token_price=fl("token_price"),
                chainlink_open_price=fl("chainlink_open_price"),
                chainlink_ref_price=fl("chainlink_ref_price"),
                chainlink_close_price=optfl("chainlink_close_price"),
                binance_mid_price=optfl("binance_mid_price"),
                sigma_intraround_per_s=fl("sigma_intraround_per_s", 0.00008),
                sigma_hourly_per_s=fl("sigma_hourly_per_s", 0.00006),
                hour_return=fl("hour_return", 0.0),
                orderbook_imbalance=fl("orderbook_imbalance", 0.0),
                bid_depth_1=fl("bid_depth_1", 0.0),
                ask_depth_1=fl("ask_depth_1", 0.0),
                source=r.get("source", "csv"),
            ))
    return out


def evaluate_observations(observations: List[Observation], config: StrategyConfig | None = None) -> List[Dict[str, object]]:
    strat = TailFlipStrategy(config)
    rows: List[Dict[str, object]] = []
    for obs in observations:
        order_type = "maker"
        ev = strat.evaluate(obs, order_type=order_type)
        d = obs.to_dict()
        d.update(ev)
        d["price_bucket"] = price_bucket(obs.token_price)
        d["order_type"] = order_type
        rows.append(d)
    deciles = assign_deciles([float(r["b_ratio"]) for r in rows])
    for r, dec in zip(rows, deciles):
        r["b_decile"] = dec
        r["price_b_decile"] = f'{r["price_bucket"]}:B{dec}'
    return rows


def summarize_backtest(rows: List[Dict[str, object]], bankroll: float = 10_000.0) -> Dict[str, object]:
    trades = [r for r in rows if bool(r.get("trade"))]
    pnl = 0.0
    risk = 0.0
    wins = 0
    for r in trades:
        price = float(r["token_price"])
        cost = break_even_cost(price, "maker")
        dollars = bankroll * 0.0005  # report uses fixed max-single-trade risk for fixture comparability
        shares = dollars / cost if cost > 0 else 0.0
        win = bool(r.get("result_win"))
        if win:
            wins += 1
            pnl += shares * (1.0 - cost)
        else:
            pnl -= shares * cost
        risk += dollars
    return {
        "observations": len(rows),
        "trades": len(trades),
        "wins": wins,
        "win_rate": wins / len(trades) if trades else 0.0,
        "gross_pnl_usd_fixed_0_05pct": pnl,
        "risked_usd": risk,
        "roi_on_risk": pnl / risk if risk else 0.0,
    }


def calibration_buckets(rows: List[Dict[str, object]]):
    return aggregate_calibration(rows, group_field="price_b_decile")
