#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from btc5m_tail_flip.aliplayer_full import build_candidates_from_aliplayer


def main() -> int:
    p = argparse.ArgumentParser(description="Build BTC 5m tail candidates from aliplayer1 full BTC files.")
    p.add_argument("--data-dir", default="data/hf_aliplayer_btc_core")
    p.add_argument("--out", default="data/real_candidates_aliplayer_btc5m_full.csv")
    p.add_argument("--progress", default="reports/aliplayer_candidate_build_progress.json")
    p.add_argument("--batch-size", type=int, default=1_000_000)
    p.add_argument("--no-dedupe-per-second", action="store_true")
    args = p.parse_args()
    data_dir = args.data_dir if os.path.isabs(args.data_dir) else os.path.join(ROOT, args.data_dir)
    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    progress = args.progress if os.path.isabs(args.progress) else os.path.join(ROOT, args.progress)
    result = build_candidates_from_aliplayer(
        markets_path=os.path.join(data_dir, "data__markets.parquet"),
        orderbook_path=os.path.join(data_dir, "data__orderbook__crypto=BTC__timeframe=5-minute__part-0.parquet"),
        spot_path=os.path.join(data_dir, "data__spot_prices__part-0.parquet"),
        out_csv=out,
        progress_path=progress,
        batch_size=args.batch_size,
        dedupe_per_second=not args.no_dedupe_per_second,
    )
    result["out"] = out
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
