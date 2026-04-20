# Final run report

Run date: 2026-04-20, Asia/Hong_Kong.

## What was actually run

### Full aliplayer BTC 5m pull

After the initial smoke run, the full BTC 5m core files from `aliplayer1/polymarket-crypto-updown` were downloaded and verified:

```text
data__markets.parquet                                      79,009 rows
data__prices__crypto=BTC__timeframe=5-minute__part-0       5,540,608 rows
data__spot_prices__part-0                                  22,802,138 rows
data__ticks__crypto=BTC__timeframe=5-minute__part-0         76,717,754 rows
data__orderbook__crypto=BTC__timeframe=5-minute__part-0     3,075,617,018 rows
```

Raw manifest:

```text
reports/aliplayer_raw_files_manifest.csv
```

The raw Parquet files are in `data/hf_aliplayer_btc_core/`. They are intentionally not included in the release zip because they are already compressed and total about 9.27 GB.

### Unit and fixture regression

Command:

```bash
./scripts/run_all_tests.sh
```

Result:

```text
Ran 22 tests in 0.001s
OK
```

Fixture regression:

```json
{
  "observations": 1098,
  "trades": 612,
  "wins": 50,
  "win_rate": 0.08169934640522876,
  "risked_usd": 3060.0,
  "roi_on_risk": 4.718954248366013,
  "warning": "Synthetic fixture only. This validates code/math, not real Polymarket profitability."
}
```

### Public HF real-data smoke regression

Downloaded source:

- `BrockMisner/polymarket-crypto-5m-15m`
- Dates: 2026-03-06 through 2026-03-13
- Tables used: `markets`, `resolutions`, `orderbooks`, `trades`, `crypto_prices`, `price_history`

Token side mapping:

- `aliplayer1/polymarket-crypto-updown`, `data/markets.parquet`

Candidate build:

```text
2026-03-06: 334
2026-03-07: 322
2026-03-08: 273
2026-03-09: 452
2026-03-10: 412
2026-03-11: 370
2026-03-12: 289
2026-03-13: 23
Total: 2475
```

Important limitation: this smoke regression uses Brock minute BTC prices as the intraround reference price. It uses market resolution labels for outcomes and can optionally fetch Gamma `priceToBeat`, but it is not a full Chainlink tick replay.

B-factor strategy calibration on all 2,475 candidates:

```json
{
  "observations": 2475,
  "trades": 1405,
  "wins": 37,
  "win_rate": 0.026334519572953737,
  "risked_usd": 7025.0,
  "gross_pnl_usd_fixed_0_05pct": 5225.0,
  "roi_on_risk": 0.7437722419928826
}
```

Queue-aware maker fill simulation:

```json
{
  "signals": 1405,
  "fills_partial_or_full": 189,
  "fill_rate": 0.13451957295373665,
  "wins_after_fill": 3,
  "win_rate_after_fill": 0.015873015873015872,
  "risk": 1340.1463182399993,
  "pnl": -260.1764682399995,
  "roi_on_risk": -0.1941403447510766
}
```

Interpretation:

- Optimistic signal-level results are positive on this public sample.
- Queue-aware simulated maker fills are negative overall.
- The only clearly positive filled bucket in this small sample is `2c:B9`, with 16 fills and 3 wins. This is too small for live approval but is useful as the next paper-trading hypothesis.

### Corrected full aliplayer replay

Important correction: orderbook `best_bid=1c/2c` is not itself a tail price. A winning token can still have a stale or low bid far below its tradable price. The corrected pipeline therefore uses `prices.up_price/down_price <= 2c` to define tail candidates, and uses orderbook only for queue-ahead.

Command path:

```bash
. .venv_duckdb/bin/activate
python scripts/build_candidates_aliplayer_duckdb.py --threads 8
PYTHONPATH=src python3 scripts/calibrate_b_factor.py data/real_candidates_aliplayer_btc5m_full.csv \
  --out reports/price_bucket_b_decile_aliplayer_btc5m_full.csv \
  --b-decile-out reports/b_decile_table_aliplayer_btc5m_full.csv \
  --evaluated-out reports/evaluated_aliplayer_btc5m_full.jsonl \
  --summary reports/backtest_summary_aliplayer_btc5m_full.json
PYTHONPATH=src python3 scripts/simulate_queue_fills_aliplayer_full.py data/real_candidates_aliplayer_btc5m_full.csv
```

Full overlap candidate build:

```json
{
  "rows": 83,
  "elapsed_s": 60.62841773033142,
  "source": "aliplayer1/polymarket-crypto-updown BTC 5m orderbook + spot_prices"
}
```

Signal-level result on those 83 true-price tail candidates:

```json
{
  "observations": 83,
  "trades": 46,
  "wins": 9,
  "win_rate": 0.1956521739130435,
  "risked_usd": 230.0,
  "roi_on_risk": 12.04347855241403
}
```

Queue-aware result using aliplayer ticks:

```json
{
  "signals": 28,
  "fills_partial_or_full": 0,
  "fill_rate": 0.0,
  "wins_after_fill": 0,
  "risk": 0.0,
  "pnl": 0.0
}
```

Interpretation: the corrected full aliplayer overlap does not prove live profitability. It suggests that true 1c/2c tail prints exist, but maker bids in the tested overlap did not get filled under the queue-aware replay.

## Output files

Core reports:

- `reports/unittest_results.txt`
- `reports/sample_backtest_summary.json`
- `reports/backtest_summary.json`
- `reports/real_backtest_summary_hf_brock_offline_2026-03-06_to_2026-03-13.json`
- `reports/price_bucket_b_decile_hf_brock_offline_2026-03-06_to_2026-03-13.csv`
- `reports/b_decile_table_hf_brock_offline_2026-03-06_to_2026-03-13.csv`
- `reports/evaluated_hf_brock_offline_2026-03-06_to_2026-03-13.jsonl`
- `reports/queue_fill_sim_hf_brock_offline_2026-03-06_to_2026-03-13.csv`
- `reports/queue_fill_sim_hf_brock_offline_2026-03-06_to_2026-03-13_summary.json`
- `reports/queue_fill_price_b_decile_hf_brock_offline.csv`
- `reports/queue_fill_b_decile_hf_brock_offline.csv`
- `reports/queue_fill_price_hf_brock_offline.csv`

Data files kept:

- `data/fixtures/btc5m_tail_fixture.csv`
- `data/real_candidates_hf_brock_offline_2026-03-06_to_2026-03-13.csv`
- per-day candidate CSVs

Large raw parquet files are intentionally excluded from the release zip. They can be restored with:

```bash
for d in 2026-03-06 2026-03-07 2026-03-08 2026-03-09 2026-03-10 2026-03-11 2026-03-12 2026-03-13; do
  PYTHONPATH=src python scripts/download_hf_btc5m.py --source brock --date "$d" --out-dir data/hf_brock
done
```

## Live readiness decision

Do not run live with the broad current gate.

Reason: queue-aware maker replay is negative/empty after correcting the tail definition. The next development step is to run paper recording against live RTDS + CLOB user fills and collect at least:

- 250 queue-aware 2c high-B fills
- posterior `P(real_prob > 2.35%) >= 80%`
- real User Channel fill confirmation
- Chainlink tick reference instead of minute proxy
