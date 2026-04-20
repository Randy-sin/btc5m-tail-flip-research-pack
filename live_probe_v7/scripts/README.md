# Scripts

`live_probe_v2_once.py` is a single-order smoke test. It defaults to dry-run and requires an explicit live confirmation string to place a real order.

Example dry run:

```bash
python scripts/live_probe_v2_once.py --token-id TOKEN_ID --condition-id CONDITION_ID
```

Example real probe order, cancel after 20s:

```bash
python scripts/live_probe_v2_once.py \
  --token-id TOKEN_ID \
  --condition-id CONDITION_ID \
  --price 0.01 \
  --size 100 \
  --cancel-after 20 \
  --live-confirm I_UNDERSTAND_THIS_USES_REAL_MONEY
```

Before using live mode, confirm your installed `py-clob-client-v2` exposes `post_order(..., post_only=True)` or equivalent. If not, adapt to the SDK's current method signature; do not place a non-post-only order for the 1c GTC probe.
