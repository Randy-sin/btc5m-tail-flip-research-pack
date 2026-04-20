# $1 Live Probe Runbook

## Goal

Turn historical proactive 1c GTC replay into real evidence by testing whether $1 post-only GTC orders actually get filled on Polymarket.

## Do not scale during probe

Probe mode is not a profit bot. It is a measurement instrument.

Hard limits:

```text
price = 0.01
size = 100 shares
risk per full fill = $1
max one open order per market side
max daily risk = $20
FOK = disabled
2c = disabled
cancel at T-6s or earlier
User Channel fill required before position accounting
```

## Recommended timeline

### Stage 0 — Security reset

1. Revoke any GitHub PAT or API key ever pasted into chat.
2. Create a dedicated Polymarket probe wallet.
3. Fund with only the amount you are willing to lose in the probe.
4. Keep `.env` off GitHub.

### Stage 1 — V2 integration dry-run

Before April 28, 2026, test V2 integration against `https://clob-v2.polymarket.com`. Do not assume it is real-money production unless Polymarket explicitly confirms.

Live mode must also pass the jurisdiction gate. The probe script calls:

```text
GET https://polymarket.com/api/geoblock
```

If the endpoint returns `blocked: true`, do not place orders from that environment.

### Stage 2 — Single-order smoke test

Post one post-only GTC 1c order, then cancel after 10–30 seconds.

Success means:

- API credentials work.
- Funder/signature type is correct.
- pUSD balance/allowance is accepted.
- Post-only order rests and can be canceled.
- User Channel and order query agree on order state.

### Stage 3 — Probe strategy

Run only when all are true:

```text
trailing_side only
B_score >= 0.58
B_ratio >= 1.15
edge_abs >= 0.0015
8s <= seconds_remaining <= 280s
best_ask > 0.01, so post-only will not cross
queue_ahead_1c not extreme, or still unknown but being measured
```

### Stage 4 — Evaluation

Minimum target before any scale:

```text
>= 7 days live probe
>= 300 actual User Channel fills, or explain why fill count is too low
actual fill rate not collapsing vs historical replay
actual win rate after fill above 1.15% with reasonable confidence
no ghost positions
cancel success >= 99%
```

Stop immediately if:

```text
User Channel / order query disagree repeatedly
orders fail to cancel before T-6s
fill rate resembles queue +1000 stress case
daily risk cap hit
post-only rejection rate indicates stale book handling
```
