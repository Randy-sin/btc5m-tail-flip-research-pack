#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from btc5m_tail_flip.backtest import read_observations_csv, evaluate_observations, summarize_backtest, calibration_buckets
from btc5m_tail_flip.calibration import write_buckets_csv


def main() -> int:
    p = argparse.ArgumentParser(description="Compute B-ratio/B-score calibration from normalized BTC5m observation CSV.")
    p.add_argument("csv", help="normalized observation CSV; use data/fixtures/btc5m_tail_fixture.csv for a smoke test")
    p.add_argument("--out", default="reports/b_factor_calibration.csv", help="price_bucket x B-decile calibration CSV")
    p.add_argument("--summary", default="reports/backtest_summary.json")
    p.add_argument("--b-decile-out", help="optional B-decile-only calibration CSV")
    p.add_argument("--evaluated-out", help="optional evaluated observation JSONL")
    args = p.parse_args()
    csv_path = args.csv if os.path.isabs(args.csv) else os.path.join(ROOT, args.csv)
    rows = evaluate_observations(read_observations_csv(csv_path))
    buckets = calibration_buckets(rows)
    out_path = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    write_buckets_csv(buckets, out_path)
    if args.b_decile_out:
        from btc5m_tail_flip.calibration import aggregate_calibration
        b_path = args.b_decile_out if os.path.isabs(args.b_decile_out) else os.path.join(ROOT, args.b_decile_out)
        os.makedirs(os.path.dirname(b_path), exist_ok=True)
        write_buckets_csv(aggregate_calibration(rows, group_field="b_decile"), b_path)
    if args.evaluated_out:
        e_path = args.evaluated_out if os.path.isabs(args.evaluated_out) else os.path.join(ROOT, args.evaluated_out)
        os.makedirs(os.path.dirname(e_path), exist_ok=True)
        with open(e_path, "w") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True) + "\n")
    summary = summarize_backtest(rows)
    summary["input_csv"] = csv_path
    summary["calibration_csv"] = out_path
    summary_path = args.summary if os.path.isabs(args.summary) else os.path.join(ROOT, args.summary)
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
