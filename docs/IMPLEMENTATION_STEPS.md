# Final implementation steps

## Phase 0 — Reproduce this package

```bash
./scripts/run_all_tests.sh
```

Verify:

- `reports/unittest_results.txt` says 14/14 tests passed.
- `reports/b_factor_calibration.csv` exists.
- `reports/evaluated_fixture_rows.jsonl` contains per-observation B-score/B-ratio decisions.

## Phase 1 — Acquire real data

Choose one or more:

1. Public snapshot repo: download Parquet snapshots from `CronosVirus00/polymarket-BTC5min-database`.
2. Paid depth data: PolyBackTest or PolyHistorical.
3. Self-record: run `collect_live_rtds_and_clob.py` for 14-100+ days.

Self-recording command:

```bash
python scripts/discover_recent_btc5m.py
python scripts/collect_live_rtds_and_clob.py --rtds --tokens UP_TOKEN_ID,DOWN_TOKEN_ID
```

## Phase 2 — Normalize

Transform raw data into `docs/DATA_SCHEMA.md`.

The normalizer must compute:

- window open price: Chainlink price-to-beat
- close price: Chainlink settlement/reference close
- per-row token price: observed 1c/2c bid/ask depending on execution mode
- volatility estimates
- orderbook depth and queue ahead
- result label

## Phase 3 — Backtest with queue-aware fills

Run calibration:

```bash
python scripts/calibrate_b_factor.py data/real_btc5m_history.csv --out reports/real_b_factor_calibration.csv --summary reports/real_backtest_summary.json
```

For GTC maker orders, additionally plug historical trade stream into `simulate_maker_buy_fill()`.

Report at least:

- optimistic fill model
- queue-aware fill model
- conservative fill model

## Phase 4 — Validate B thresholds

Primary table:

```text
price_bucket × B_decile × fill_model
```

Promote a bucket only if:

```text
actual queue-aware fill win rate > all-in break-even
posterior P(edge > threshold) >= 80%
```

## Phase 5 — Paper trade

Run at least 14 days with:

- real RTDS Chainlink
- real CLOB market channel
- no money orders or tiny test orders only
- User Channel fill confirmation tested separately
- every signal/order/fill/reject raw logged

## Phase 6 — Small LIVE

Start with:

- 1c maker only
- no FOK
- max single trade 0.05% bankroll
- max window risk 0.10%
- daily tail risk 0.60%
- kill switch enabled

Only add 2c maker / FOK after live fill behavior matches paper.
