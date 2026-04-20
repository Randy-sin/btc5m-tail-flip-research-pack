# BTC5M Tail Flip — Live Probe V7 Add-on

This add-on converts the proactive 1c GTC replay result into a small-money live probe plan.

It is **not** a full production bot and defaults to dry-run mode. Real order placement requires an explicit confirmation flag.

Core goal: verify whether historical proactive 1c GTC fills translate into real Polymarket User Channel fills.

Local validation report:

```text
docs/VALIDATION_REPORT_20260420.md
```

Current local result: SDK inspection and dry-run passed, but live execution from this machine is blocked by Polymarket geoblock (`US / NY`), so no live order was placed. Do not run live orders from a blocked jurisdiction or try to bypass geoblocking.
