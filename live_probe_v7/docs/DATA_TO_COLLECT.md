# Data Required During Live Probe

For every market:

- market slug
- condition_id
- UP token ID
- DOWN token ID
- window start/end
- Chainlink open/ref/close
- Binance ref
- orderbook full or best available snapshots
- 1c bid size before order
- all order IDs
- order post timestamp
- cancel timestamp
- User Channel fill timestamp
- filled shares
- avg fill price
- resolved side
- pnl

For every strategy decision:

- side
- B_score
- B_ratio
- model_prob
- break_even
- edge_abs
- seconds_remaining
- reason accepted/rejected

The most important derived variables:

- actual queue_ahead_1c
- actual fill_rate by queue bucket
- win_rate_after_fill by queue bucket
- time from post to first fill
- time from fill to close
