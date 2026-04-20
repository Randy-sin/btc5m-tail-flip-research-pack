#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from btc5m_tail_flip.data_sources import public_snapshot_raw_url


def main() -> int:
    p = argparse.ArgumentParser(description="Download public GitHub parquet snapshots from CronosVirus00/polymarket-BTC5min-database.")
    p.add_argument("filenames", nargs="+", help="parquet filenames, e.g. btc-updown-5m-1776323400_1776323446.parquet")
    p.add_argument("--out-dir", default="data/public_snapshots")
    args = p.parse_args()
    try:
        import requests
    except Exception as e:
        raise SystemExit(f"requests not installed: {e}")
    out_dir = args.out_dir if os.path.isabs(args.out_dir) else os.path.join(ROOT, args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    for name in args.filenames:
        url = public_snapshot_raw_url(name)
        out_path = os.path.join(out_dir, name)
        print(f"GET {url}")
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(r.content)
        print(f"wrote {out_path} ({len(r.content)} bytes)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
