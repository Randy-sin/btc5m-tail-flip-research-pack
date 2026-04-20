from __future__ import annotations

"""Full BTC 5m candidate and fill pipeline for aliplayer1 HF data."""

import csv
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from .backtest import TradeEvent, evaluate_observations, read_observations_csv, simulate_maker_buy_fill
from .core import Observation
from .synthetic import FIELDS


EXTRA_FIELDS = ["condition_id", "token_id", "settled_side", "queue_ahead", "best_ask"]


@dataclass(frozen=True)
class SpotSeries:
    ts: np.ndarray
    price: np.ndarray
    sigma_i: np.ndarray
    sigma_h: np.ndarray
    hour_return: np.ndarray


def safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def load_btc5m_markets(markets_path: str):
    import pandas as pd

    cols = [
        "market_id", "crypto", "timeframe", "end_ts", "condition_id",
        "up_token_id", "down_token_id",
    ]
    df = pd.read_parquet(markets_path, columns=cols)
    df = df[(df["crypto"] == "BTC") & (df["timeframe"] == "5-minute")].copy()
    df["market_id"] = df["market_id"].astype(str)
    df["window_end_ts"] = df["end_ts"].astype("int64")
    df["window_start_ts"] = df["window_end_ts"] - 300
    markets = {
        str(r.market_id): {
            "condition_id": str(r.condition_id),
            "up_token_id": str(r.up_token_id),
            "down_token_id": str(r.down_token_id),
            "window_start_ts": int(r.window_start_ts),
            "window_end_ts": int(r.window_end_ts),
        }
        for r in df.itertuples(index=False)
    }
    token_side: Dict[str, Tuple[str, str]] = {}
    for mid, meta in markets.items():
        token_side[str(meta["up_token_id"])] = (mid, "UP")
        token_side[str(meta["down_token_id"])] = (mid, "DOWN")
    return markets, token_side


def load_spot_series(spot_path: str) -> SpotSeries:
    import pandas as pd
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    chunks = []
    pf = pq.ParquetFile(spot_path)
    for batch in pf.iter_batches(batch_size=1_000_000, columns=["ts_ms", "symbol", "price", "source"]):
        table = pa.Table.from_batches([batch])
        symbol = table["symbol"]
        mask = pc.equal(symbol, "btc/usd")
        table = table.filter(mask)
        if table.num_rows:
            chunks.append(table.to_pandas())
    if not chunks:
        raise RuntimeError("No btc/usd rows found in spot_prices")
    df = pd.concat(chunks, ignore_index=True)
    df["ts"] = (df["ts_ms"].astype("int64") // 1000).astype("int64")
    df = df.sort_values("ts").drop_duplicates("ts", keep="last")
    df["price"] = df["price"].astype(float)
    logp = np.log(df["price"].to_numpy())
    logret = np.diff(logp, prepend=logp[0])
    # Count windows are intentionally conservative: spot feed cadence can vary.
    sigma_i = pd.Series(logret).rolling(300, min_periods=10).std().fillna(0.00008).to_numpy()
    sigma_h = pd.Series(logret).rolling(3600, min_periods=60).std().fillna(0.00006).to_numpy()
    hour_return = pd.Series(logp).diff(3600).fillna(0.0).to_numpy()
    return SpotSeries(
        ts=df["ts"].to_numpy(dtype=np.int64),
        price=df["price"].to_numpy(dtype=float),
        sigma_i=np.maximum(sigma_i, 1e-7),
        sigma_h=np.maximum(sigma_h, 1e-7),
        hour_return=hour_return,
    )


def nearest_values(series: SpotSeries, ts_values: np.ndarray):
    idx = np.searchsorted(series.ts, ts_values, side="right") - 1
    idx = np.clip(idx, 0, len(series.ts) - 1)
    return (
        series.price[idx],
        series.sigma_i[idx],
        series.sigma_h[idx],
        series.hour_return[idx],
    )


def nearest_price(series: SpotSeries, ts_values: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(series.ts, ts_values, side="right") - 1
    idx = np.clip(idx, 0, len(series.ts) - 1)
    return series.price[idx]


def build_candidates_from_aliplayer(
    markets_path: str,
    orderbook_path: str,
    spot_path: str,
    out_csv: str,
    max_seconds_remaining: int = 120,
    min_seconds_remaining: int = 8,
    batch_size: int = 1_000_000,
    progress_path: Optional[str] = None,
    dedupe_per_second: bool = True,
) -> Dict[str, object]:
    import pandas as pd
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    markets, _token_side = load_btc5m_markets(markets_path)
    spot = load_spot_series(spot_path)

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    fields = FIELDS + EXTRA_FIELDS
    counts = {"batches": 0, "candidate_rows": 0, "raw_tail_rows": 0, "deduped_rows": 0}
    seen = set()
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        pf = pq.ParquetFile(orderbook_path)
        for batch in pf.iter_batches(
            batch_size=batch_size,
            columns=["ts_ms", "market_id", "token_id", "outcome", "best_bid", "best_ask", "best_bid_size", "best_ask_size"],
        ):
            counts["batches"] += 1
            table = pa.Table.from_batches([batch])
            mask = pc.and_(pc.greater_equal(table["best_bid"], 0.009999), pc.less_equal(table["best_bid"], 0.020001))
            table = table.filter(mask)
            counts["raw_tail_rows"] += table.num_rows
            if not table.num_rows:
                continue
            df = table.to_pandas()
            df["ts"] = (df["ts_ms"].astype("int64") // 1000).astype("int64")
            # BTC 5m windows are aligned to 300-second boundaries. Filtering by
            # inferred seconds remaining before metadata joins avoids millions
            # of Python dict lookups on irrelevant tail-book rows.
            df["window_end_ts"] = ((df["ts"] // 300) + 1) * 300
            df["seconds_remaining"] = df["window_end_ts"] - df["ts"]
            df = df[
                (df["seconds_remaining"] >= min_seconds_remaining)
                & (df["seconds_remaining"] <= max_seconds_remaining)
            ].copy()
            if df.empty:
                continue
            df["market_id"] = df["market_id"].astype(str)
            df["known_end_ts"] = df["market_id"].map(lambda m: markets.get(m, {}).get("window_end_ts"))
            df = df[df["known_end_ts"].notna()].copy()
            if df.empty:
                continue
            df["known_end_ts"] = df["known_end_ts"].astype("int64")
            df = df[df["known_end_ts"] == df["window_end_ts"]].copy()
            if df.empty:
                continue
            df["window_start_ts"] = df["window_end_ts"] - 300

            ts = df["ts"].to_numpy(dtype=np.int64)
            start_ts = df["window_start_ts"].to_numpy(dtype=np.int64)
            end_ts = df["window_end_ts"].to_numpy(dtype=np.int64)
            ref, sigma_i, sigma_h, hour_return = nearest_values(spot, ts)
            open_px = nearest_price(spot, start_ts)
            close_px = nearest_price(spot, end_ts)

            for i, r in enumerate(df.itertuples(index=False)):
                if dedupe_per_second:
                    key = (str(r.market_id), str(r.token_id), int(ts[i]), round(float(r.best_bid) * 100))
                    if key in seen:
                        counts["deduped_rows"] += 1
                        continue
                    seen.add(key)
                meta = markets[str(r.market_id)]
                settled_side = "UP" if close_px[i] >= open_px[i] else "DOWN"
                bid = float(r.best_bid_size or 0.0)
                ask = float(r.best_ask_size or 0.0)
                imbalance = safe_div(bid - ask, bid + ask)
                row = {
                    "market_id": str(r.market_id),
                    "ts": int(ts[i]),
                    "window_start_ts": int(start_ts[i]),
                    "window_end_ts": int(end_ts[i]),
                    "side": str(r.outcome).upper(),
                    "token_price": float(r.best_bid),
                    "chainlink_open_price": float(open_px[i]),
                    "chainlink_ref_price": float(ref[i]),
                    "chainlink_close_price": float(close_px[i]),
                    "binance_mid_price": "",
                    "sigma_intraround_per_s": float(sigma_i[i]),
                    "sigma_hourly_per_s": float(sigma_h[i]),
                    "hour_return": float(hour_return[i]),
                    "orderbook_imbalance": max(-1.0, min(1.0, imbalance)),
                    "bid_depth_1": bid,
                    "ask_depth_1": ask,
                    "source": "hf_aliplayer_full:orderbook_bbo:spot_btc_usd",
                    "condition_id": meta["condition_id"],
                    "token_id": str(r.token_id),
                    "settled_side": settled_side,
                    "queue_ahead": bid,
                    "best_ask": float(r.best_ask) if r.best_ask is not None else "",
                }
                writer.writerow(row)
                counts["candidate_rows"] += 1
            if progress_path and counts["batches"] % 10 == 0:
                with open(progress_path, "w") as pfw:
                    json.dump(counts, pfw, indent=2, sort_keys=True)
    if progress_path:
        with open(progress_path, "w") as pfw:
            json.dump(counts, pfw, indent=2, sort_keys=True)
    return counts


def load_candidate_extras(path: str):
    extras = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            extras.append({
                "token_id": row.get("token_id", ""),
                "queue_ahead": float(row.get("queue_ahead") or 0.0),
            })
    return extras


def load_aliplayer_tail_trades(ticks_path: str, token_ids: Iterable[str], max_price: float = 0.020001) -> Dict[str, List[TradeEvent]]:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    token_values = pa.array(list(set(token_ids)))
    by_token: Dict[str, List[TradeEvent]] = defaultdict(list)
    pf = pq.ParquetFile(ticks_path)
    for batch in pf.iter_batches(
        batch_size=1_000_000,
        columns=["timestamp_ms", "token_id", "side", "price", "size_usdc"],
    ):
        table = pa.Table.from_batches([batch])
        mask = pc.and_(
            pc.and_(pc.is_in(table["token_id"], value_set=token_values), pc.equal(table["side"], "SELL")),
            pc.less_equal(table["price"], max_price),
        )
        table = table.filter(mask)
        if not table.num_rows:
            continue
        for r in table.to_pylist():
            price = float(r["price"])
            size_usdc = float(r["size_usdc"] or 0.0)
            size_shares = size_usdc / price if price > 0 else 0.0
            by_token[str(r["token_id"])].append(TradeEvent(
                ts=int(int(r["timestamp_ms"]) // 1000),
                price=price,
                size=size_shares,
                side="SELL",
            ))
    for trades in by_token.values():
        trades.sort(key=lambda tr: tr.ts)
    return by_token


def simulate_aliplayer_queue_fills(
    candidates_csv: str,
    ticks_path: str,
    out_csv: str,
    summary_path: str,
    shares: float = 500.0,
    dedupe_market_side_price: bool = True,
) -> Dict[str, object]:
    extras = load_candidate_extras(candidates_csv)
    rows = evaluate_observations(read_observations_csv(candidates_csv))
    token_ids = [extra["token_id"] for row, extra in zip(rows, extras) if bool(row.get("trade"))]
    by_token = load_aliplayer_tail_trades(ticks_path, token_ids)

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    fields = [
        "market_id", "ts", "side", "token_price", "token_id", "trade_signal",
        "result_win", "queue_ahead", "filled", "fill_fraction", "filled_ts", "pnl",
    ]
    seen = set()
    signals = fills = wins = 0
    filled_shares = pnl = risk = 0.0
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row, extra in zip(rows, extras):
            if not bool(row.get("trade")):
                continue
            key = (row["market_id"], row["side"], round(float(row["token_price"]) * 100))
            if dedupe_market_side_price and key in seen:
                continue
            seen.add(key)
            signals += 1
            order_ts = int(row["ts"])
            cancel_ts = int(row["window_end_ts"]) - 6
            token_id = str(extra["token_id"])
            trades = [tr for tr in by_token.get(token_id, []) if order_ts < tr.ts <= cancel_ts]
            res = simulate_maker_buy_fill(
                order_ts=order_ts,
                limit_price=float(row["token_price"]),
                size=shares,
                queue_ahead=float(extra["queue_ahead"]),
                trades_after=trades,
            )
            win = bool(row.get("result_win"))
            trade_pnl = 0.0
            if res.filled > 0:
                fills += 1
                filled_shares += res.filled
                cost = res.filled * float(row["token_price"])
                risk += cost
                trade_pnl = (res.filled if win else 0.0) - cost
                pnl += trade_pnl
                if win:
                    wins += 1
            writer.writerow({
                "market_id": row["market_id"],
                "ts": row["ts"],
                "side": row["side"],
                "token_price": row["token_price"],
                "token_id": token_id,
                "trade_signal": True,
                "result_win": win,
                "queue_ahead": extra["queue_ahead"],
                "filled": res.filled,
                "fill_fraction": res.fill_fraction,
                "filled_ts": res.filled_ts if res.filled_ts is not None else "",
                "pnl": trade_pnl,
            })
    summary = {
        "candidate_csv": candidates_csv,
        "ticks_path": ticks_path,
        "signals": signals,
        "fills_partial_or_full": fills,
        "fill_rate": fills / signals if signals else 0.0,
        "filled_shares": filled_shares,
        "wins_after_fill": wins,
        "win_rate_after_fill": wins / fills if fills else 0.0,
        "risk": risk,
        "pnl": pnl,
        "roi_on_risk": pnl / risk if risk else 0.0,
        "dedupe_market_side_price": dedupe_market_side_price,
        "warning": "Uses aliplayer ticks side as taker perspective and size_usdc/price as shares.",
    }
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    return summary
