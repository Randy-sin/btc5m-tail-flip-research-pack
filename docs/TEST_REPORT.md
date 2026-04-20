# Test report

See `docs/FINAL_RUN_REPORT.md` for the final completed run.

Generated in this sandbox with:

```bash
cd /mnt/data/btc5m_tail_flip_research_pack
./scripts/run_all_tests.sh
```

## Unit tests

Result: **14 tests passed**.

Covered:

- crypto taker fee formula
- maker/taker break-even
- Kelly sizing
- terminal binary probability estimate
- B-score and B-ratio monotonicity/definition
- strategy gates for 1c maker and too-late rejection
- queue-aware maker fill simulation
- Wilson interval and Bayesian posterior helper
- calibration aggregation

Output file:

```text
reports/unittest_results.txt
```

## Fixture backtest

The fixture is deterministic synthetic data, not historical Polymarket data.

Summary from `reports/sample_backtest_summary.json`:

```json
{
  "fixture_rows_written": 1098,
  "observations": 1098,
  "trades": 612,
  "wins": 50,
  "win_rate": 0.08169934640522876,
  "gross_pnl_usd_fixed_0_05pct": 14440.0,
  "risked_usd": 3060.0,
  "roi_on_risk": 4.718954248366013,
  "warning": "Synthetic fixture only. This validates code/math, not real Polymarket profitability."
}
```

The fixture intentionally has tail-flip cases so that B-factor and calibration logic can be regression-tested. It must **not** be interpreted as real expected ROI.

## B-factor calculation outputs

- `reports/b_factor_calibration.csv`
- `reports/b_factor_calibration_fixture.csv`
- `reports/evaluated_fixture_rows.jsonl`

The calibration table groups evaluated rows by:

```text
price_bucket × B_decile
```

Example table columns:

```text
key, observations, trades, wins, win_rate, wilson_low, wilson_high, break_even, edge_abs, posterior_prob_edge_positive
```

## What remains untested without real data

- Actual 1c/2c touch frequency.
- Queue-aware maker fill rate from real trade prints.
- Real settled win rate after Chainlink close.
- Cancel latency and ghost-position handling.
- Edge decay over time.
