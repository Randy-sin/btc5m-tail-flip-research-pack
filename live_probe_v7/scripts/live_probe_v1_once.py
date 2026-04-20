#!/usr/bin/env python3
"""Single-order Polymarket CLOB V1 production probe.

Use this only while production trading is still on the V1 CLOB endpoint.
It mirrors the V2 probe: one post-only GTC BUY at 1c, optional timed cancel,
and default dry-run mode unless the explicit live confirmation string is set.
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

import requests

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
LIVE_CONFIRM = "I_UNDERSTAND_THIS_USES_REAL_MONEY"
USDC_DECIMALS = 1_000_000


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
    size_shares: float
    tick_size: str
    neg_risk: bool
    cancel_after_s: int
    live: bool


def _api_creds_from_env():
    from py_clob_client.clob_types import ApiCreds

    api_key = os.getenv("POLY_API_KEY") or os.getenv("POLY_CLOB_API_KEY") or os.getenv("CLOB_API_KEY")
    api_secret = os.getenv("POLY_SECRET") or os.getenv("POLY_CLOB_SECRET") or os.getenv("CLOB_SECRET")
    api_passphrase = (
        os.getenv("POLY_PASSPHRASE")
        or os.getenv("POLY_CLOB_PASSPHRASE")
        or os.getenv("CLOB_PASS_PHRASE")
    )
    if api_key and api_secret and api_passphrase:
        return ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_passphrase)
    return None


def build_client(cfg: ProbeConfig):
    try:
        from py_clob_client.client import ClobClient
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("py-clob-client is not installed. Run: pip install py-clob-client") from exc

    client = ClobClient(
        host=cfg.host,
        chain_id=cfg.chain_id,
        key=cfg.private_key,
        signature_type=cfg.signature_type,
        funder=cfg.funder_address,
    )
    creds = _api_creds_from_env()
    if creds is None:
        if hasattr(client, "create_or_derive_api_creds"):
            creds = client.create_or_derive_api_creds()
        else:
            creds = client.create_api_key(nonce=0)
    client.set_api_creds(creds)
    return client


def check_geoblock_or_raise() -> dict[str, Any]:
    resp = requests.get("https://polymarket.com/api/geoblock", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("blocked") is True:
        raise RuntimeError(f"Polymarket geoblock rejected this location: {json.dumps(data, sort_keys=True)}")
    if "blocked" not in data:
        raise RuntimeError(f"Unexpected geoblock response: {json.dumps(data, sort_keys=True)}")
    return data


def collateral_balance_micro(client: Any, cfg: ProbeConfig) -> int:
    from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

    params = BalanceAllowanceParams(
        asset_type=AssetType.COLLATERAL,
        signature_type=cfg.signature_type,
    )
    data = client.get_balance_allowance(params)
    return int(data.get("balance") or 0)


def create_and_post_post_only_gtc(client: Any, cfg: ProbeConfig) -> dict[str, Any]:
    from py_clob_client.clob_types import OrderArgs, OrderType, PartialCreateOrderOptions
    from py_clob_client.order_builder.constants import BUY

    order_args = OrderArgs(
        token_id=cfg.token_id,
        price=cfg.price,
        size=cfg.size_shares,
        side=BUY,
    )
    options = PartialCreateOrderOptions(tick_size=cfg.tick_size, neg_risk=cfg.neg_risk)
    signed = client.create_order(order_args, options=options)
    return client.post_order(signed, OrderType.GTC, post_only=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token-id", required=True)
    parser.add_argument("--condition-id", default=None)
    parser.add_argument("--price", type=float, default=float(os.getenv("PROBE_ORDER_PRICE", "0.01")))
    parser.add_argument("--size", type=float, default=float(os.getenv("PROBE_ORDER_SIZE_SHARES", "100")))
    parser.add_argument("--tick-size", default="0.01")
    parser.add_argument("--neg-risk", action="store_true")
    parser.add_argument("--cancel-after", type=int, default=int(os.getenv("PROBE_CANCEL_AFTER_SECONDS", "30")))
    parser.add_argument("--host", default=os.getenv("POLY_V1_HOST", "https://clob.polymarket.com"))
    parser.add_argument("--chain-id", type=int, default=int(os.getenv("POLY_CHAIN_ID", "137")))
    parser.add_argument("--signature-type", type=int, default=int(os.getenv("POLY_SIGNATURE_TYPE", "1")))
    parser.add_argument("--funder", default=os.getenv("POLY_FUNDER_ADDRESS", ""))
    parser.add_argument("--live-confirm", default="")
    return parser.parse_args()


def main() -> int:
    _load_env()
    args = parse_args()
    live = args.live_confirm == LIVE_CONFIRM
    cfg = ProbeConfig(
        host=args.host,
        chain_id=args.chain_id,
        private_key=os.getenv("POLY_PRIVATE_KEY") or os.getenv("PK") or os.getenv("PRIVATE_KEY") or "",
        funder_address=args.funder,
        signature_type=args.signature_type,
        token_id=args.token_id,
        condition_id=args.condition_id,
        price=args.price,
        size_shares=args.size,
        tick_size=args.tick_size,
        neg_risk=bool(args.neg_risk),
        cancel_after_s=args.cancel_after,
        live=live,
    )

    risk = cfg.price * cfg.size_shares
    print({
        "mode": "LIVE" if live else "DRY_RUN",
        "host": cfg.host,
        "condition_id": cfg.condition_id,
        "token_id": cfg.token_id,
        "price": cfg.price,
        "size_shares": cfg.size_shares,
        "max_collateral_units_if_full_fill": risk,
        "post_only": True,
        "order_type": "GTC",
        "cancel_after_s": cfg.cancel_after_s,
    })

    if not live:
        print(f"Dry-run only. Add --live-confirm {LIVE_CONFIRM} to place a real order.")
        return 0
    if not cfg.private_key or not cfg.funder_address:
        print("Missing POLY_PRIVATE_KEY or POLY_FUNDER_ADDRESS", file=sys.stderr)
        return 2

    geoblock = check_geoblock_or_raise()
    print({"geoblock": geoblock})

    client = build_client(cfg)
    balance = collateral_balance_micro(client, cfg)
    required = int(risk * USDC_DECIMALS)
    print({"collateral_balance_micro": balance, "required_micro": required})
    if balance < required:
        raise RuntimeError("Insufficient collateral balance for requested probe order")

    response = create_and_post_post_only_gtc(client, cfg)
    print({"post_response": response})
    order_id = response.get("orderID") or response.get("order_id") or response.get("id")
    if order_id and cfg.cancel_after_s > 0:
        time.sleep(cfg.cancel_after_s)
        cancel_resp = client.cancel(order_id)
        print({"cancel_response": cancel_resp})
    else:
        print("No order id found, or cancel_after <= 0. Check order manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
