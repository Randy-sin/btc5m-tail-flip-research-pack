#!/usr/bin/env python3
"""
Single-order Polymarket CLOB V2 probe.

Default mode is dry-run. To place a real order, pass:

  --live-confirm I_UNDERSTAND_THIS_USES_REAL_MONEY

This script is intentionally narrow: one post-only GTC BUY at 1c, optional timed cancel.
It is meant for API/signer/funder/allowance validation before running a strategy loop.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    if load_dotenv:
        load_dotenv(dotenv_path=PACKAGE_ROOT / ".env")


@dataclass
class ProbeConfig:
    host: str
    chain_id: int
    private_key: str
    funder_address: str
    signature_type: int
    token_id: str
    condition_id: Optional[str]
    price: float
    size: float
    tick_size: str
    neg_risk: bool
    cancel_after_s: int
    live: bool


def build_client(cfg: ProbeConfig):
    """Create py-clob-client-v2 client. Kept isolated because SDK APIs are still moving."""
    try:
        from py_clob_client_v2 import ApiCreds, ClobClient
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "py-clob-client-v2 is not installed. Run: pip install py-clob-client-v2"
        ) from exc

    api_key = os.getenv("POLY_CLOB_API_KEY") or os.getenv("CLOB_API_KEY")
    api_secret = os.getenv("POLY_CLOB_SECRET") or os.getenv("CLOB_SECRET")
    api_passphrase = os.getenv("POLY_CLOB_PASSPHRASE") or os.getenv("CLOB_PASS_PHRASE")

    # Derive API creds if not provided.
    if api_key and api_secret and api_passphrase:
        creds = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_passphrase)
    else:
        temp = ClobClient(
            host=cfg.host,
            chain_id=cfg.chain_id,
            key=cfg.private_key,
            signature_type=cfg.signature_type,
            funder=cfg.funder_address,
        )
        creds = temp.create_or_derive_api_key()

    return ClobClient(
        host=cfg.host,
        chain_id=cfg.chain_id,
        key=cfg.private_key,
        creds=creds,
        signature_type=cfg.signature_type,
        funder=cfg.funder_address,
    )


def create_and_post_post_only_gtc(client: Any, cfg: ProbeConfig) -> dict[str, Any]:
    try:
        from py_clob_client_v2 import OrderArgs, OrderType, PartialCreateOrderOptions, Side
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("py-clob-client-v2 import failed") from exc

    order_args = OrderArgs(
        token_id=cfg.token_id,
        price=cfg.price,
        side=Side.BUY,
        size=cfg.size,
    )
    options = PartialCreateOrderOptions(tick_size=cfg.tick_size, neg_risk=cfg.neg_risk)

    # py-clob-client-v2 supports post-only through postOrder/postOrders. If create_and_post_order
    # in your installed version does not expose post_only, use create_order + post_order below.
    try:
        signed = client.create_order(order_args=order_args, options=options)
        return client.post_order(signed, order_type=OrderType.GTC, post_only=True)
    except TypeError:
        # Fallback for SDK builds where post_only kw is named postOnly or absent.
        # In that case DO NOT continue blindly in live mode, because maker-only is required.
        raise RuntimeError(
            "Installed py-clob-client-v2 did not accept post_only=True on post_order. "
            "Inspect SDK method signature before using real money."
        )


def cancel_order(client: Any, order_id: str) -> Any:
    try:
        from py_clob_client_v2 import OrderPayload
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("py-clob-client-v2 import failed for OrderPayload") from exc

    payload = OrderPayload(orderID=order_id)
    for name in ("cancel_order", "cancelOrder"):
        fn = getattr(client, name, None)
        if fn:
            return fn(payload)
    raise RuntimeError("SDK client has no cancel_order method in this version")


def check_geoblock_or_raise() -> dict[str, Any]:
    """Fail closed before any live order if Polymarket says this IP is blocked.

    Official endpoint:
      GET https://polymarket.com/api/geoblock

    Dry-run mode does not call this. Live mode must be explicit and should not
    place orders when the endpoint is unavailable or returns non-JSON.
    """
    import requests

    url = "https://polymarket.com/api/geoblock"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("blocked") is True:
        raise RuntimeError(f"Polymarket geoblock rejected this location: {json.dumps(data, sort_keys=True)}")
    if "blocked" not in data:
        raise RuntimeError(f"Unexpected geoblock response: {json.dumps(data, sort_keys=True)}")
    return data


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--token-id", required=True, help="Outcome token ID to buy at 1c")
    p.add_argument("--condition-id", default=None, help="Market condition ID, for logging only")
    p.add_argument("--price", type=float, default=float(os.getenv("PROBE_ORDER_PRICE", "0.01")))
    p.add_argument("--size", type=float, default=float(os.getenv("PROBE_ORDER_SIZE_SHARES", "100")))
    p.add_argument("--tick-size", default="0.01")
    p.add_argument("--neg-risk", action="store_true")
    p.add_argument("--cancel-after", type=int, default=int(os.getenv("PROBE_CANCEL_AFTER_SECONDS", "30")))
    p.add_argument("--host", default=os.getenv("POLY_HOST", "https://clob-v2.polymarket.com"))
    p.add_argument("--chain-id", type=int, default=int(os.getenv("POLY_CHAIN_ID", "137")))
    p.add_argument("--signature-type", type=int, default=int(os.getenv("POLY_SIGNATURE_TYPE", "2")))
    p.add_argument("--funder", default=os.getenv("POLY_FUNDER_ADDRESS", ""))
    p.add_argument("--live-confirm", default="", help="Must equal I_UNDERSTAND_THIS_USES_REAL_MONEY")
    return p.parse_args()


def main() -> int:
    _load_env()
    args = parse_args()
    pk = os.getenv("POLY_PRIVATE_KEY") or os.getenv("PK") or os.getenv("PRIVATE_KEY") or ""
    live = args.live_confirm == "I_UNDERSTAND_THIS_USES_REAL_MONEY"

    cfg = ProbeConfig(
        host=args.host,
        chain_id=args.chain_id,
        private_key=pk,
        funder_address=args.funder,
        signature_type=args.signature_type,
        token_id=args.token_id,
        condition_id=args.condition_id,
        price=args.price,
        size=args.size,
        tick_size=args.tick_size,
        neg_risk=bool(args.neg_risk),
        cancel_after_s=args.cancel_after,
        live=live,
    )

    risk = cfg.price * cfg.size
    print({
        "mode": "LIVE" if live else "DRY_RUN",
        "host": cfg.host,
        "condition_id": cfg.condition_id,
        "token_id": cfg.token_id,
        "price": cfg.price,
        "size_shares": cfg.size,
        "risk_usd_if_full_fill": risk,
        "post_only": True,
        "order_type": "GTC",
        "cancel_after_s": cfg.cancel_after_s,
    })

    if not live:
        print("Dry-run only. Add --live-confirm I_UNDERSTAND_THIS_USES_REAL_MONEY to place a real order.")
        return 0

    if not pk or not cfg.funder_address:
        print("Missing POLY_PRIVATE_KEY or POLY_FUNDER_ADDRESS", file=sys.stderr)
        return 2

    geoblock = check_geoblock_or_raise()
    print({"geoblock": geoblock})

    client = build_client(cfg)
    response = create_and_post_post_only_gtc(client, cfg)
    print({"post_response": response})

    order_id = response.get("orderID") or response.get("order_id") or response.get("id")
    if order_id and cfg.cancel_after_s > 0:
        time.sleep(cfg.cancel_after_s)
        cancel_resp = cancel_order(client, order_id)
        print({"cancel_response": cancel_resp})
    else:
        print("No order id found, or cancel_after <= 0. Check order manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
