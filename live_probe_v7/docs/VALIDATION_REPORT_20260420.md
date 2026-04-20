# Live Probe V7 Validation Report

Run date: 2026-04-20.

## Package

```text
source: /Users/randy/Downloads/btc5m-tail-flip-live-probe-v7-20260420.zip
sha256: 34f43c905cf0e227b010b6a533dde5e271c0f78d139a25bd32cf7f382b6e8f5c
```

## Local Checks

The live probe dependency set installs successfully in a temporary virtual environment:

```text
py-clob-client-v2==1.0.0
requests>=2.31.0
websockets>=12.0
python-dotenv>=1.0.0
```

`scripts/live_probe_v2_once.py` compiles successfully.

The installed `py-clob-client-v2` SDK exposes the maker-only call path needed by this probe:

```text
ClobClient.post_order(order, order_type='GTC', post_only: bool = False, defer_exec: bool = False)
ClobClient.create_and_post_order(..., order_type='GTC', post_only: bool = False, defer_exec: bool = False)
```

One SDK mismatch was fixed before committing this package:

```text
cancel_order() expects OrderPayload(orderID=...), not a raw order id string.
```

## Dry Run

Dry-run mode does not require private keys and does not place an order:

```text
python scripts/live_probe_v2_once.py \
  --token-id TEST_TOKEN \
  --condition-id TEST_CONDITION \
  --price 0.01 \
  --size 100 \
  --cancel-after 20
```

Expected output:

```text
mode: DRY_RUN
post_only: True
order_type: GTC
risk_usd_if_full_fill: 1.0
```

## Geoblock Result

Before any live order, the script now calls:

```text
GET https://polymarket.com/api/geoblock
```

The current execution environment was blocked:

```text
blocked: true
country: US
region: NY
```

Therefore no live order was placed from this machine.

Do not run live orders from a blocked jurisdiction. Do not attempt to bypass geoblocking. The $1 live probe must only be run from an eligible jurisdiction, with the user responsible for account, wallet, funding, tax, and regulatory compliance.

## Current Status

Ready for:

```text
dry-run parameter validation
SDK signature inspection
repo review
eligible-jurisdiction live smoke test, only after explicit confirmation
```

Not ready for:

```text
live execution from this current machine/location
automated trading loop
FOK/taker execution
larger than $1 probe orders
```
