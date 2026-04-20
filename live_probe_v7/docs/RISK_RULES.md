# Probe Risk Rules

Probe bankroll should be separate from main funds.

## Jurisdiction gate

Before any live order, the probe must call Polymarket's geoblock endpoint and fail closed if the current location is blocked:

```text
GET https://polymarket.com/api/geoblock
```

Do not run live orders from a blocked jurisdiction and do not attempt to bypass geoblocking. Dry-run mode may still be used for local parameter validation because it does not place or sign a live order.

Default limits:

```text
single order: 100 shares at 0.01 = $1 risk
max open orders: 1 until smoke test passes, then 2 max (UP/DOWN across different markets)
max daily filled risk: $20
max daily posted risk: $100 reserved pUSD
cancel before T-6s
no FOK in probe phase
no 2c taker in probe phase
no martingale
```

Decision thresholds after live probe:

```text
Continue:
  actual fills >= 100 and no execution incidents

Promote to small-live:
  actual fills >= 300
  actual win_rate_after_fill > 1.15%
  queue-depth behavior not equivalent to +1000 stress case
  cancel success >= 99%

Halt:
  actual fill_rate < 5% for multiple active days
  200 actual fills with 0 wins
  User Channel state unreliable
  repeated cancel failures
```
