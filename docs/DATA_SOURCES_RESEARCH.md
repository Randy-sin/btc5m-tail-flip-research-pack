# Data-source research notes

This package separates real-data acquisition from model testing because historical Polymarket CLOB/Chainlink data is fragmented.

## Official public endpoints

### Gamma market discovery

- Base: `https://gamma-api.polymarket.com`
- Market by slug: `/markets/slug/{slug}`
- Use: discover condition ID, UP/DOWN token IDs, market status and metadata.

### CLOB price history

- Base: `https://clob.polymarket.com`
- Endpoint: `/prices-history`
- Parameters: `market` (actually token ID), `startTs`, `endTs`, `interval`, `fidelity`.
- Limitation: this gives price time-series, not queue/depth. It cannot prove 1c/2c maker fillability.

### CLOB market WebSocket

- Endpoint: `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- Subscribe by token IDs.
- Required for live orderbook, price changes, trades and market resolved events.

### RTDS Chainlink/Binance

- Endpoint: `wss://ws-live-data.polymarket.com`
- Topics: `crypto_prices_chainlink`, `crypto_prices`.
- Use Chainlink as settlement anchor; Binance only as reference/nowcast.

## Public data found

### aliplayer1/polymarket-crypto-updown

- Public Hugging Face dataset.
- Covers crypto up/down markets across BTC, ETH, SOL, BNB, XRP, DOGE and HYPE.
- The dataset card lists subsets for `markets`, `prices`, `ticks`, `spot_prices` and `orderbook`.
- The BTC 5-minute core files observed on 2026-04-20 are large:
  - `data/orderbook/crypto=BTC/timeframe=5-minute/part-0.parquet`: about 6.49 GB
  - `data/ticks/crypto=BTC/timeframe=5-minute/part-0.parquet`: about 2.64 GB
  - `data/spot_prices/part-0.parquet`: about 130 MB
  - `data/prices/crypto=BTC/timeframe=5-minute/part-0.parquet`: about 11.8 MB
- This package uses `data/markets.parquet` for token side mapping because it contains `up_token_id` and `down_token_id`.
- Parallel downloader included: `scripts/download_aliplayer_btc_core_parallel.py`.

### BrockMisner/polymarket-crypto-5m-15m

- Public Hugging Face dataset.
- Covers BTC/ETH/SOL/XRP 5-minute and 15-minute up/down markets.
- Contains daily `orderbooks`, `trades`, `price_history`, `crypto_prices`, plus `markets/all.parquet` and `resolutions/all.parquet`.
- Used for the completed public smoke regression because the daily slices are small enough to run locally.
- Date range run locally: 2026-03-06 through 2026-03-13.

### CronosVirus00/polymarket-BTC5min-database

- Public GitHub repository.
- Contains BTC 5m orderbook snapshots.
- Format: Apache Parquet.
- README says files include Unix timestamp, slug, asset id, top 100 bids, top 100 asks and raw orderbook.
- Downloader included: `scripts/download_public_orderbook_snapshots.py`.

Example filename observed in repo:

```text
btc-updown-5m-1776323400_1776323446.parquet
```

## Paid/commercial sources found

### PolyBackTest

- Claims real historical orderbook depth, sub-second snapshots, Binance prices and market metadata.
- Good for orderbook-accurate replay, slippage and fill simulation.

### PolyHistorical

- Claims tick-by-tick orderbook replay for BTC/ETH/SOL Up/Down markets.

## Known limitations and caveats

1. Official `/prices-history` is not enough for maker strategy because it lacks queue-ahead and depth.
2. An undocumented `/orderbook-history` endpoint has public reports of returning empty data for recent post-Feb 2026 windows; the code includes it only as best-effort.
3. Chainlink Data Streams are easy to collect live through Polymarket RTDS but large historical Chainlink-aligned settlement series may require a vendor or self-recording.
4. Any claimed profitability must be recomputed after normalizing a real dataset into `docs/DATA_SCHEMA.md`.
5. BrockMisner daily data is good enough for public smoke testing, but its `crypto_prices` table is used as a reference proxy. It is not a substitute for full Chainlink tick replay.
