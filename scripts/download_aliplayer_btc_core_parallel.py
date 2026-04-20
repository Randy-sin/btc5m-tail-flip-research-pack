#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
from typing import List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from btc5m_tail_flip.hf_ingest import ALIPLAYER_REPO, download_file, hf_resolve_url, safe_local_name


CORE_PATHS = [
    "data/markets.parquet",
    "data/prices/crypto=BTC/timeframe=5-minute/part-0.parquet",
    "data/spot_prices/part-0.parquet",
    "data/ticks/crypto=BTC/timeframe=5-minute/part-0.parquet",
    "data/orderbook/crypto=BTC/timeframe=5-minute/part-0.parquet",
]


def target_path(out_dir: str, remote_path: str) -> str:
    return os.path.join(out_dir, safe_local_name(remote_path))


def main() -> int:
    p = argparse.ArgumentParser(description="Parallel downloader for aliplayer1 BTC 5m core files.")
    p.add_argument("--out-dir", default="data/hf_aliplayer_btc_core")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--dry-run", action="store_true", help="Print URLs and target files without downloading.")
    args = p.parse_args()

    out_dir = args.out_dir if os.path.isabs(args.out_dir) else os.path.join(ROOT, args.out_dir)
    jobs = [(path, target_path(out_dir, path), hf_resolve_url(ALIPLAYER_REPO, path)) for path in CORE_PATHS]
    if args.dry_run:
        print(json.dumps([{"remote_path": p, "target": t, "url": u} for p, t, u in jobs], indent=2))
        return 0

    os.makedirs(out_dir, exist_ok=True)
    results: List[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        future_map = {ex.submit(download_file, ALIPLAYER_REPO, remote, local, 3600.0): remote for remote, local, _ in jobs}
        for fut in concurrent.futures.as_completed(future_map):
            result = fut.result()
            record = result.__dict__
            print(json.dumps(record, sort_keys=True))
            results.append(record)
    manifest = os.path.join(out_dir, "download_manifest.json")
    with open(manifest, "w") as f:
        json.dump(results, f, indent=2, sort_keys=True)
    print(json.dumps({"manifest": manifest, "files": len(results)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
