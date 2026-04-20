# Polymarket CLOB V2 Research Notes

Research date: 2026-04-20.

## V2 migration status

Polymarket docs say CLOB V2 go-live is April 28, 2026 around 11:00 UTC, with about 1 hour of downtime. Open orders will be wiped during cutover. Before cutover, test against `https://clob-v2.polymarket.com`; after cutover, V2 takes over `https://clob.polymarket.com`.

## SDK

Use V2 SDK only:

```bash
pip install py-clob-client-v2
# or TypeScript:
# npm install @polymarket/clob-client-v2 ethers@5
```

Do not build new work on legacy `py-clob-client` for a system intended to survive the April 28 cutover.

## V2 changes relevant to the bot

- Collateral changes from USDC.e to pUSD.
- API-only traders may need to wrap USDC.e into pUSD via CollateralOnramp.
- Order uniqueness uses timestamp in milliseconds; old nonce fields are removed in V2 order struct.
- `feeRateBps`, `nonce`, and `taker` are removed from order creation.
- Fees are protocol-set at match time; do not hardcode fee bps into signed orders.
- Makers are not charged platform fees; takers pay dynamic platform fees.
- `getClobMarketInfo(conditionID)` returns minimum tick size, minimum order size, fee details, and token metadata.
- Builder fees are additive. Do not attach a builder code in probe mode unless intentionally testing builder routing economics.

## Wallet type

- Signature type 0: standalone EOA, funder is EOA address, needs POL for gas.
- Signature type 1: Polymarket proxy via Magic Link.
- Signature type 2: Gnosis Safe / browser-wallet proxy; most common for Polymarket.com users.

If funds are visible in a Polymarket.com account, use the proxy wallet funder address and signature type 1 or 2, not type 0.

## Order types

- GTC/GTD are resting limit orders.
- FOK/FAK are immediate market order types.
- Post-only can be used only with GTC/GTD.
- A post-only order that crosses the spread is rejected, which is exactly what we want for maker-only probe orders.

## WebSocket subscriptions

- Market channel uses token IDs / asset IDs.
- User channel uses condition IDs, not token IDs.
- RTDS Chainlink BTC symbol is `btc/usd`.
- RTDS Binance BTC symbol is `btcusdt`.

## Practical implication for this strategy

The probe should place post-only GTC BUY at 0.01, size 100 shares ($1 notional risk), on the trailing side only. REST order accepted does **not** mean filled. Only User Channel trade/match events or order query showing matched size should count as a real fill.
