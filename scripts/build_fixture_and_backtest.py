#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from btc5m_tail_flip.synthetic import write_fixture_csv
from btc5m_tail_flip.backtest import read_observations_csv, evaluate_observations, summarize_backtest, calibration_buckets
from btc5m_tail_flip.calibration import write_buckets_csv


def main() -> int:
    data_path = os.path.join(ROOT, "data", "fixtures", "btc5m_tail_fixture.csv")
    report_dir = os.path.join(ROOT, "reports")
    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    os.makedirs(report_dir, exist_ok=True)
    n = write_fixture_csv(data_path, n_markets=160, seed=42)
    observations = read_observations_csv(data_path)
    rows = evaluate_observations(observations)
    summary = summarize_backtest(rows, bankroll=10_000.0)
    summary["fixture_rows_written"] = n
    summary["warning"] = "Synthetic fixture only. This validates code/math, not real Polymarket profitability."
    with open(os.path.join(report_dir, "sample_backtest_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    buckets = calibration_buckets(rows)
    write_buckets_csv(buckets, os.path.join(report_dir, "b_factor_calibration_fixture.csv"))
    with open(os.path.join(report_dir, "evaluated_fixture_rows.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
