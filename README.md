# BTC 5m Tail Flip Research Pack

This package is a tested research/backtest scaffold for the Polymarket BTC 5m tail-flip strategy based on:

1. Price-structure/B-factor idea from the article: buy 1c/2c tails only when market compression creates positive EV.
2. Engineering constraints from the BTC 5m technical guide: Chainlink anchor, Polymarket CLOB, maker-first execution, queue-aware fill logic, and strict risk controls.

## Important status

- Unit/regression tests have been run locally in this package.
- A public Hugging Face smoke regression has also been run on BrockMisner BTC 5m/15m data from 2026-03-06 through 2026-03-13.
- The included CSV is a deterministic synthetic fixture used to test math and code paths. It is **not** a real historical-performance proof.
- The public smoke run is useful, but not a full Chainlink tick replay. Full CLOB/Chainlink historical orderbook backtests require one of:
  - a paid orderbook data source such as PolyBackTest/PolyHistorical;
  - the public GitHub Parquet snapshots listed in docs/DATA_SOURCES_RESEARCH.md;
  - your own RTDS + CLOB recorder running for 14-100+ days.

Read the completed run report first:

```bash
cat docs/FINAL_RUN_REPORT.md
```

Live decision from the completed run: do not run the broad gate live. Queue-aware maker fills are negative overall on the public 8-day smoke sample; the next paper-only hypothesis is the narrower `2c:B9` bucket.

Update: the aliplayer BTC 5m core files have now also been fully downloaded and processed. The corrected aliplayer replay defines tail candidates from `prices.up_price/down_price <= 2c`, not from raw orderbook `best_bid`, because a 1c low bid can exist on non-tail tokens. The corrected overlap produced 83 true-price candidates and 0 queue-aware maker fills. See `docs/FINAL_RUN_REPORT.md`.

## Run everything

```bash
cd btc5m_tail_flip_research_pack
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 scripts/build_fixture_and_backtest.py
/usr/bin/python3 scripts/calibrate_b_factor.py data/fixtures/btc5m_tail_fixture.csv
```

Or:

```bash
./scripts/run_all_tests.sh
```

## Key outputs already generated

- `reports/unittest_results.txt`: 22 tests, all passed.
- `reports/sample_backtest_summary.json`: synthetic fixture smoke-test summary.
- `reports/b_factor_calibration.csv`: B-ratio/B-score bucket table generated from the fixture.
- `reports/evaluated_fixture_rows.jsonl`: every evaluated synthetic observation with model probability, B-score, B-ratio, edge and decision.
- `reports/real_backtest_summary_hf_brock_offline_2026-03-06_to_2026-03-13.json`: public HF signal-level smoke regression.
- `reports/queue_fill_sim_hf_brock_offline_2026-03-06_to_2026-03-13_summary.json`: public HF queue-aware maker fill replay.
- `reports/aliplayer_raw_files_manifest.csv`: full aliplayer BTC 5m raw file row counts.
- `reports/backtest_summary_aliplayer_btc5m_full.json`: corrected full aliplayer signal-level replay.
- `reports/queue_fill_sim_aliplayer_btc5m_full_summary.json`: corrected full aliplayer queue-aware replay.

## Normalized real-data input schema

See `docs/DATA_SCHEMA.md`. Once your real data is normalized into that schema, run:

```bash
/usr/bin/python3 scripts/calibrate_b_factor.py data/real_btc5m_history.csv --out reports/real_b_factor_calibration.csv --summary reports/real_backtest_summary.json
```

## Public data collection entry points

```bash
# Discover recent BTC 5m markets and token IDs via Gamma API
/usr/bin/python3 scripts/discover_recent_btc5m.py

# Download public parquet snapshots from CronosVirus00/polymarket-BTC5min-database
/usr/bin/python3 scripts/download_public_orderbook_snapshots.py btc-updown-5m-1776323400_1776323446.parquet

# Collect live RTDS Chainlink/Binance + optional CLOB market channel
/usr/bin/python3 scripts/collect_live_rtds_and_clob.py --rtds --tokens TOKEN_UP,TOKEN_DOWN
```

Public Hugging Face smoke pipeline:

```bash
for d in 2026-03-06 2026-03-07 2026-03-08 2026-03-09 2026-03-10 2026-03-11 2026-03-12 2026-03-13; do
  PYTHONPATH=src python scripts/download_hf_btc5m.py --source brock --date "$d" --out-dir data/hf_brock
  PYTHONPATH=src python scripts/build_candidates_from_hf.py --date "$d" --out "data/real_candidates_hf_brock_offline_$d.csv"
done

PYTHONPATH=src python scripts/calibrate_b_factor.py \
  data/real_candidates_hf_brock_offline_2026-03-06_to_2026-03-13.csv \
  --out reports/price_bucket_b_decile_hf_brock_offline_2026-03-06_to_2026-03-13.csv \
  --b-decile-out reports/b_decile_table_hf_brock_offline_2026-03-06_to_2026-03-13.csv \
  --evaluated-out reports/evaluated_hf_brock_offline_2026-03-06_to_2026-03-13.jsonl

PYTHONPATH=src python scripts/simulate_queue_fills_from_hf.py \
  data/real_candidates_hf_brock_offline_2026-03-06_to_2026-03-13.csv
```

## What has been tested

- Polymarket crypto taker fee formula and maker/taker break-even.
- Binary terminal probability estimator.
- B-score and B-ratio calculation.
- Strategy gating for 1c/2c maker and FOK disabled path.
- Queue-aware maker fill simulator.
- Wilson confidence interval and Bayesian edge-posterior helper.
- Synthetic fixture generation and B-factor calibration pipeline.

## What still requires real historical data

- Actual 1c/2c tail touch frequency.
- Queue-aware maker fill rate at 1c/2c.
- Real settled flip rate by `price_bucket × B_decile`.
- Slippage and cancel latency.
- Edge decay across time segments and market sessions.
