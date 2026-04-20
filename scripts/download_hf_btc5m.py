#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from btc5m_tail_flip.hf_ingest import (
    download_aliplayer_markets,
    download_brock_day,
    write_download_manifest,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Download public HF Polymarket BTC 5m research data.")
    p.add_argument("--source", choices=["brock", "aliplayer-markets"], default="brock")
    p.add_argument("--date", default="2026-03-13", help="Brock daily slice date, YYYY-MM-DD")
    p.add_argument("--out-dir", default="data/hf_brock")
    p.add_argument("--manifest", default="reports/hf_download_manifest.json")
    args = p.parse_args()

    out_dir = args.out_dir if os.path.isabs(args.out_dir) else os.path.join(ROOT, args.out_dir)
    if args.source == "brock":
        files = download_brock_day(args.date, out_dir)
    else:
        files = [download_aliplayer_markets(out_dir)]
    manifest = args.manifest if os.path.isabs(args.manifest) else os.path.join(ROOT, args.manifest)
    write_download_manifest(files, manifest)
    print(json.dumps([f.__dict__ for f in files], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
