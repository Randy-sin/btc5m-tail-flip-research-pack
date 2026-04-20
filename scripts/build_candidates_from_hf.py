#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from btc5m_tail_flip.candidate_builder import build_candidates_from_brock


def main() -> int:
    p = argparse.ArgumentParser(description="Build normalized BTC5m 1c/2c tail candidates from public HF data.")
    p.add_argument("--brock-dir", default="data/hf_brock")
    p.add_argument("--aliplayer-markets", default="data/hf_aliplayer/markets.parquet")
    p.add_argument("--date", default="2026-03-13")
    p.add_argument("--out", default="data/real_candidates_hf_brock_2026-03-13.csv")
    p.add_argument("--gamma-cache", default="data/cache/gamma_btc5m_meta.json")
    p.add_argument("--fetch-gamma", action="store_true", help="Fetch Gamma priceToBeat and cache it.")
    args = p.parse_args()

    brock_dir = args.brock_dir if os.path.isabs(args.brock_dir) else os.path.join(ROOT, args.brock_dir)
    aliplayer = args.aliplayer_markets if os.path.isabs(args.aliplayer_markets) else os.path.join(ROOT, args.aliplayer_markets)
    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    cache = args.gamma_cache if os.path.isabs(args.gamma_cache) else os.path.join(ROOT, args.gamma_cache)
    n = build_candidates_from_brock(
        orderbooks_path=os.path.join(brock_dir, f"orderbooks__{args.date}.parquet"),
        crypto_prices_path=os.path.join(brock_dir, f"crypto_prices__{args.date}.parquet"),
        resolutions_path=os.path.join(brock_dir, "resolutions__all.parquet"),
        aliplayer_markets_path=aliplayer,
        out_csv=out,
        gamma_cache_path=cache,
        fetch_gamma=args.fetch_gamma,
    )
    print(json.dumps({"candidates": n, "out": out, "gamma_cache": cache}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
