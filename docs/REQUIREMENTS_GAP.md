# Requirement gaps found and added

The original brief and guide contain the core strategy, but a production-quality implementation also needs the following explicit requirements.

## 1. Provenance and replayability

Every signal must be traceable to raw messages:

- RTDS Chainlink raw JSONL
- RTDS Binance raw JSONL
- CLOB market channel raw JSONL
- Gamma market metadata JSON
- final settlement record

Without raw replay, B-factor changes cannot be audited.

## 2. Queue-aware maker fills

For 1c/2c GTC maker orders, touch price is not enough. The backtest must model queue ahead and later taker-sell volume at or below the maker bid.

Included implementation: `simulate_maker_buy_fill()` in `src/btc5m_tail_flip/backtest.py`.

## 3. Strict distinction: order posted vs filled

REST order success means the order is live/resting, not filled. In LIVE mode, position is recognized only after User Channel trade/match confirmation.

## 4. B-factor calibration acceptance criteria

Minimum acceptance for real data:

- 1c maker: `P(real_prob > 1.15%) >= 80%`, at least 300 queue-aware fills.
- 2c maker: `P(real_prob > 2.35%) >= 80%`, at least 250 queue-aware fills.
- 2c FOK/taker: `P(real_prob > 2.75%) >= 80%`, at least 300 fills and measured slippage.

## 5. Data staleness circuit breakers

Stop trading when:

- Chainlink RTDS stale > configured threshold.
- CLOB market channel stale.
- local clock drift > 1s.
- Gamma metadata missing current/next token IDs.
- fee schedule or market fee flag cannot be verified.

## 6. Walk-forward only

Do not random-split observations. Use time-sorted walk-forward windows to avoid future leakage.

## 7. Separate maker and taker performance

The strategy is maker-first. FOK/taker samples must be reported separately because the all-in break-even and selection bias differ.
