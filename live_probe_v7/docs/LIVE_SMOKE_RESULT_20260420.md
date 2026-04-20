# Live Smoke Result - 2026-04-20

This note records the first real-money queue smoke test run from the fresh
server directory:

`/home/ubuntu/btc5m_live_probe_fresh_20260420_0704/live_probe_v7`

## What Was Verified

- Server SSH worked with `poly.pem`.
- A fresh isolated folder was created; the old project directory was not
  modified.
- The existing probe `.env` was migrated into the fresh folder with mode
  `600`.
- Required private-key/funder/signature fields were present.
- CLOB V2 API credentials could be derived, but V2 collateral balance was `0`.
- CLOB V1 production collateral balance was nonzero and sufficient for a `$1`
  smoke test.

## V2 Status

V2 host:

`https://clob-v2.polymarket.com`

Read-only checks passed:

- `geoblock.blocked = false`
- current/next BTC 5m Gamma discovery worked
- CLOB V2 `get_market` worked
- `minimum_tick_size = 0.01`
- `minimum_order_size = 5`
- `accepting_orders = true`

Blocking issue for live V2 probe:

- collateral balance: `0`
- collateral allowance: `0`

Conclusion: V2 is technically reachable, but this wallet/funder currently has
no usable V2 collateral for a live `$1` order.

## V1 Live Smoke Test

Because V1 production still had collateral available, one real-money smoke test
was run against:

`https://clob.polymarket.com`

Order intent:

- market: BTC 5m next window
- outcome: Down
- side: BUY
- price: `0.01`
- size: `100` shares
- maximum full-fill risk: `$1.00`
- order type: GTC
- post-only: true
- cancel after: `20` seconds

Result:

- post response success: `true`
- initial order status: `live`
- cancel response: order id returned under `canceled`
- post-check status: `CANCELED`
- matched size: `0`
- collateral balance after post-check: unchanged at `4025977` micro-units

Order ID:

`0x433b0728ba4e1e641203c899867ec8b6201528bdd45587fc29b35fdf6940ae15`

Post-check report on server:

`reports/live_smoke_v1_20260420_0720_postcheck.json`

## Interpretation

This validates the first operational milestone:

- real order submission works;
- post-only GTC can rest on the book;
- timed cancellation works;
- no fill occurred during the smoke test;
- no ghost position was observed.

This does **not** yet validate the strategy edge. It only validates that a
real `$1` order can enter and leave the CLOB safely.

## Next Step

The next milestone is a controlled live queue probe loop:

- still `$1` per order;
- only proactive `1c` GTC;
- only one open order at a time;
- hard daily filled-risk cap;
- every order/fill/cancel written to a durable report file;
- User Channel or `get_order` post-check required before treating a fill as
  real.
