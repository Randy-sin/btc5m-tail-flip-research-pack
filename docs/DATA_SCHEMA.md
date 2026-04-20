# Normalized BTC 5m observation schema

Every row is one candidate observation for one token side at one timestamp.

| field | type | required | meaning |
|---|---:|---:|---|
| market_id | str | yes | slug or market identifier, e.g. `btc-updown-5m-1776323400` |
| ts | int | yes | observation Unix seconds |
| window_start_ts | int | yes | BTC 5m window start Unix seconds |
| window_end_ts | int | yes | window_start_ts + 300 |
| side | str | yes | `UP` or `DOWN` |
| token_price | float | yes | observed or simulated entry price, e.g. 0.01/0.02 |
| chainlink_open_price | float | yes | Chainlink price-to-beat / window open |
| chainlink_ref_price | float | yes | Chainlink-current or Chainlink-nowcast reference at `ts` |
| chainlink_close_price | float | backtest yes | Chainlink settlement price for the window |
| binance_mid_price | float | optional | Binance reference/nowcast, not settlement truth |
| sigma_intraround_per_s | float | yes | realized volatility estimate per sqrt-second |
| sigma_hourly_per_s | float | yes | hourly EWMA volatility per sqrt-second |
| hour_return | float | optional | BTC 1h return for trend filter |
| orderbook_imbalance | float | optional | [-1,+1] token orderbook imbalance |
| bid_depth_1 | float | optional | depth at best bid or at entry price |
| ask_depth_1 | float | optional | depth at best ask |
| source | str | optional | data provenance |

Outcome label:

```python
UP wins   iff chainlink_close_price >= chainlink_open_price
DOWN wins iff chainlink_close_price <  chainlink_open_price
```

This schema is deliberately independent of any one data vendor. Convert Gamma/CLOB/RTDS/Parquet data into this table first, then run `scripts/calibrate_b_factor.py`.
