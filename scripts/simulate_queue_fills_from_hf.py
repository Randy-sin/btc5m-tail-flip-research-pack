#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from btc5m_tail_flip.backtest import TradeEvent, read_observations_csv, evaluate_observations, simulate_maker_buy_fill


def epoch_seconds(value) -> int:
    import pandas as pd
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return int(ts.timestamp())


def load_candidate_extras(path: str):
    extras = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            extras.append({
                "token_id": row.get("token_id", ""),
                "queue_ahead": float(row.get("queue_ahead") or 0.0),
                "condition_id": row.get("condition_id", ""),
                "settled_side": row.get("settled_side", ""),
            })
    return extras


def load_trades(paths):
    try:
        import pandas as pd
    except Exception as e:
        raise SystemExit("pandas/pyarrow required for HF parquet trades") from e
    frames = []
    for path in paths:
        df = pd.read_parquet(path, columns=["timestamp", "asset", "token_id", "side", "price", "size"])
        df = df[df["asset"] == "BTC"].copy()
        df["epoch"] = df["timestamp"].map(epoch_seconds)
        frames.append(df)
    if not frames:
        return {}
    all_trades = pd.concat(frames, ignore_index=True).sort_values("epoch")
    by_token = defaultdict(list)
    for r in all_trades.itertuples(index=False):
        by_token[str(r.token_id)].append(TradeEvent(
            ts=int(r.epoch),
            price=float(r.price),
            size=float(r.size),
            side=str(r.side),
        ))
    return by_token


def main() -> int:
    p = argparse.ArgumentParser(description="Queue-aware maker fill simulation for HF Brock trade data.")
    p.add_argument("candidates_csv")
    p.add_argument("--trades-glob", default="data/hf_brock/trades__2026-03-*.parquet")
    p.add_argument("--shares", type=float, default=500.0, help="simulated shares per signal")
    p.add_argument("--out", default="reports/queue_fill_sim_hf_brock.csv")
    p.add_argument("--summary", default="reports/queue_fill_sim_hf_brock_summary.json")
    args = p.parse_args()

    candidate_path = args.candidates_csv if os.path.isabs(args.candidates_csv) else os.path.join(ROOT, args.candidates_csv)
    trade_glob = args.trades_glob if os.path.isabs(args.trades_glob) else os.path.join(ROOT, args.trades_glob)
    trade_paths = sorted(glob.glob(trade_glob))
    extras = load_candidate_extras(candidate_path)
    evaluated = evaluate_observations(read_observations_csv(candidate_path))
    by_token = load_trades(trade_paths)

    out_path = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    fields = [
        "market_id", "ts", "side", "token_price", "token_id", "trade_signal",
        "result_win", "queue_ahead", "filled", "fill_fraction", "filled_ts", "pnl",
    ]
    signals = fills = wins = 0
    filled_shares = pnl = risk = 0.0
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row, extra in zip(evaluated, extras):
            if not bool(row.get("trade")):
                continue
            signals += 1
            token_id = str(extra["token_id"])
            order_ts = int(row["ts"])
            cancel_ts = int(row["window_end_ts"]) - 6
            trades = [tr for tr in by_token.get(token_id, []) if order_ts < tr.ts <= cancel_ts]
            res = simulate_maker_buy_fill(
                order_ts=order_ts,
                limit_price=float(row["token_price"]),
                size=float(args.shares),
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
                "trade_signal": bool(row.get("trade")),
                "result_win": win,
                "queue_ahead": extra["queue_ahead"],
                "filled": res.filled,
                "fill_fraction": res.fill_fraction,
                "filled_ts": res.filled_ts if res.filled_ts is not None else "",
                "pnl": trade_pnl,
            })

    summary = {
        "candidate_csv": candidate_path,
        "trade_files": trade_paths,
        "signals": signals,
        "fills_partial_or_full": fills,
        "fill_rate": fills / signals if signals else 0.0,
        "filled_shares": filled_shares,
        "wins_after_fill": wins,
        "win_rate_after_fill": wins / fills if fills else 0.0,
        "risk": risk,
        "pnl": pnl,
        "roi_on_risk": pnl / risk if risk else 0.0,
        "warning": "Queue simulation assumes Brock trade `side` is taker side. Validate against raw CLOB user fills before live trading.",
    }
    summary_path = args.summary if os.path.isabs(args.summary) else os.path.join(ROOT, args.summary)
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
