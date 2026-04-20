#!/usr/bin/env python3
"""Discover current/next BTC 5m Polymarket IDs for the live probe.

This is a read-only helper. It fetches Gamma metadata by the canonical
``btc-updown-5m-{window_ts}`` slug and optionally cross-checks the CLOB V2
market info endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
SLUG_PREFIX = "btc-updown-5m-"
WINDOW_SECONDS = 300


def _load_env() -> None:
    if load_dotenv:
        load_dotenv(dotenv_path=PACKAGE_ROOT / ".env")


def _parse_jsonish(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _market_from_gamma(slug: str) -> dict[str, Any]:
    resp = requests.get(GAMMA_MARKETS_URL, params={"slug": slug}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    items = data if isinstance(data, list) else [data]
    for item in items:
        if item.get("slug") == slug or item.get("market_slug") == slug:
            return item
    if len(items) == 1:
        return items[0]
    raise RuntimeError(f"Gamma returned no exact market for slug={slug}")


def _extract_tokens(market: dict[str, Any]) -> dict[str, str]:
    raw_tokens = _parse_jsonish(market.get("tokens") or market.get("clobTokenIds") or [])
    outcomes = _parse_jsonish(market.get("outcomes") or [])

    up = ""
    down = ""
    if isinstance(raw_tokens, list) and raw_tokens and isinstance(raw_tokens[0], dict):
        for token in raw_tokens:
            outcome = str(token.get("outcome") or "").lower()
            token_id = str(token.get("token_id") or token.get("tokenId") or "")
            if outcome == "up":
                up = token_id
            elif outcome == "down":
                down = token_id
    elif isinstance(raw_tokens, list) and len(raw_tokens) >= 2:
        if isinstance(outcomes, list) and len(outcomes) >= 2:
            for idx, outcome in enumerate(outcomes[:2]):
                label = str(outcome).lower()
                if label == "up":
                    up = str(raw_tokens[idx])
                elif label == "down":
                    down = str(raw_tokens[idx])
        if not up or not down:
            up, down = str(raw_tokens[0]), str(raw_tokens[1])

    if not up or not down:
        raise RuntimeError(f"Could not extract UP/DOWN token ids from market: {market.get('slug')}")
    return {"up_token_id": up, "down_token_id": down}


def _clob_market_info(condition_id: str) -> dict[str, Any]:
    from py_clob_client_v2 import ClobClient

    host = os.getenv("POLY_HOST", "https://clob-v2.polymarket.com")
    chain_id = int(os.getenv("POLY_CHAIN_ID", "137"))
    client = ClobClient(host=host, chain_id=chain_id)
    info = client.get_market(condition_id)
    if not isinstance(info, dict):
        return {"raw_type": str(type(info))}
    return {
        "accepting_orders": info.get("accepting_orders"),
        "enable_order_book": info.get("enable_order_book"),
        "minimum_order_size": info.get("minimum_order_size"),
        "minimum_tick_size": info.get("minimum_tick_size"),
        "neg_risk": info.get("neg_risk"),
        "tokens": info.get("tokens"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", choices=["current", "next"], default="current")
    parser.add_argument("--offset-windows", type=int, default=0)
    parser.add_argument("--window-ts", type=int, default=None)
    parser.add_argument("--with-clob-info", action="store_true")
    return parser.parse_args()


def main() -> int:
    _load_env()
    args = parse_args()
    now = int(time.time())
    base = (now // WINDOW_SECONDS) * WINDOW_SECONDS
    if args.window == "next":
        base += WINDOW_SECONDS
    window_ts = args.window_ts if args.window_ts is not None else base + args.offset_windows * WINDOW_SECONDS
    slug = f"{SLUG_PREFIX}{window_ts}"

    market = _market_from_gamma(slug)
    tokens = _extract_tokens(market)
    condition_id = market.get("conditionId") or market.get("condition_id") or ""
    if not condition_id:
        raise RuntimeError(f"No condition id for slug={slug}")

    result: dict[str, Any] = {
        "slug": slug,
        "window_ts": window_ts,
        "condition_id": condition_id,
        "up_token_id": tokens["up_token_id"],
        "down_token_id": tokens["down_token_id"],
        "question": market.get("question"),
        "end_date": market.get("endDate") or market.get("end_date_iso"),
        "seconds_remaining": max(0, window_ts + WINDOW_SECONDS - now),
        "active": market.get("active"),
        "closed": market.get("closed"),
    }
    if args.with_clob_info:
        result["clob_market_info"] = _clob_market_info(condition_id)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print({"error": type(exc).__name__, "message": str(exc)}, file=sys.stderr)
        raise
