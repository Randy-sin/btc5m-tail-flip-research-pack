#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from btc5m_tail_flip.aliplayer_full import simulate_aliplayer_queue_fills


def main() -> int:
    p = argparse.ArgumentParser(description="Queue-aware fill replay using aliplayer1 BTC 5m ticks.")
    p.add_argument("candidates_csv", nargs="?", default="data/real_candidates_aliplayer_btc5m_full.csv")
    p.add_argument("--data-dir", default="data/hf_aliplayer_btc_core")
    p.add_argument("--shares", type=float, default=500.0)
    p.add_argument("--out", default="reports/queue_fill_sim_aliplayer_btc5m_full.csv")
    p.add_argument("--summary", default="reports/queue_fill_sim_aliplayer_btc5m_full_summary.json")
    p.add_argument("--no-dedupe", action="store_true")
    args = p.parse_args()
    data_dir = args.data_dir if os.path.isabs(args.data_dir) else os.path.join(ROOT, args.data_dir)
    candidates = args.candidates_csv if os.path.isabs(args.candidates_csv) else os.path.join(ROOT, args.candidates_csv)
    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    summary = args.summary if os.path.isabs(args.summary) else os.path.join(ROOT, args.summary)
    result = simulate_aliplayer_queue_fills(
        candidates_csv=candidates,
        ticks_path=os.path.join(data_dir, "data__ticks__crypto=BTC__timeframe=5-minute__part-0.parquet"),
        out_csv=out,
        summary_path=summary,
        shares=args.shares,
        dedupe_market_side_price=not args.no_dedupe,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
