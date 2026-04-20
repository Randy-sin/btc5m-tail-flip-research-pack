#!/usr/bin/env python3
"""V1 proactive 1c GTC live probe loop.

This is intentionally narrow and small:

- V1 production CLOB only;
- BUY trailing-side token at 0.01;
- post-only GTC;
- default size is 5 shares, so max locked collateral is 0.05;
- one open order at a time;
- cancel before T-6s;
- JSONL audit log for every decision/order/cancel/postcheck.

It is a queue/fill probe, not a production trading bot.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any, Optional

import requests
import websockets

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
RTDS_URL = "wss://ws-live-data.polymarket.com"
WINDOW_SECONDS = 300
SLUG_PREFIX = "btc-updown-5m-"
USDC_DECIMALS = 1_000_000


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


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


def log_jsonl(path: Path, event: dict[str, Any]) -> None:
    event.setdefault("ts", time.time())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


@dataclass
class Market:
    slug: str
    window_ts: int
    condition_id: str
    up_token_id: str
    down_token_id: str
    end_ts: int


@dataclass
class OpenOrder:
    order_id: str
    market: Market
    side: str
    token_id: str
    price: float
    size_shares: float
    created_ts: float
    filled_shares_seen: float = 0.0


class ChainlinkState:
    def __init__(self) -> None:
        self.last_price: Optional[float] = None
        self.last_event_ts: Optional[float] = None
        self.last_arrival_ts: Optional[float] = None
        self.ticks: list[tuple[float, float]] = []

    def on_message(self, msg: dict[str, Any]) -> bool:
        payload = msg.get("payload")
        if isinstance(payload, dict):
            msg = payload
        symbol = str(msg.get("symbol") or "").lower()
        if symbol != "btc/usd":
            return False
        value = msg.get("value", msg.get("price"))
        ts_raw = msg.get("timestamp", msg.get("ts", int(time.time() * 1000)))
        try:
            price = float(value)
            event_ts = float(ts_raw)
        except (TypeError, ValueError):
            return False
        if event_ts > 10_000_000_000:
            event_ts /= 1000.0
        self.last_price = price
        self.last_event_ts = event_ts
        self.last_arrival_ts = time.time()
        self.ticks.append((event_ts, price))
        cutoff = time.time() - 3900
        self.ticks = [(ts, px) for ts, px in self.ticks if ts >= cutoff]
        return True

    def open_for_window(self, window_ts: int) -> Optional[float]:
        for ts, px in self.ticks:
            if ts >= window_ts:
                return px
        return None

    def sigma_per_s(self, since_ts: float, default: float) -> float:
        pts = [(ts, px) for ts, px in self.ticks if ts >= since_ts and px > 0]
        if len(pts) < 4:
            return default
        vals: list[float] = []
        for (t0, p0), (t1, p1) in zip(pts, pts[1:]):
            dt = max(1e-3, t1 - t0)
            r = math.log(p1 / p0)
            vals.append((r * r) / dt)
        if not vals:
            return default
        return max(1e-7, math.sqrt(fmean(vals)))

    def hour_return(self) -> float:
        if self.last_price is None:
            return 0.0
        target = time.time() - 3600
        older = None
        for ts, px in self.ticks:
            if ts <= target:
                older = px
            else:
                break
        if older is None or older <= 0:
            return 0.0
        return math.log(self.last_price / older)


def discover_market(window_ts: int) -> Market:
    slug = f"{SLUG_PREFIX}{window_ts}"
    resp = requests.get(GAMMA_MARKETS_URL, params={"slug": slug}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    items = data if isinstance(data, list) else [data]
    market = None
    for item in items:
        if item.get("slug") == slug or item.get("market_slug") == slug:
            market = item
            break
    if market is None and len(items) == 1:
        market = items[0]
    if market is None:
        raise RuntimeError(f"Gamma returned no exact market for {slug}")

    tokens = _parse_jsonish(market.get("tokens") or market.get("clobTokenIds") or [])
    outcomes = _parse_jsonish(market.get("outcomes") or [])
    up = down = ""
    if isinstance(tokens, list) and tokens and isinstance(tokens[0], dict):
        for token in tokens:
            label = str(token.get("outcome") or "").lower()
            token_id = str(token.get("token_id") or token.get("tokenId") or "")
            if label == "up":
                up = token_id
            elif label == "down":
                down = token_id
    elif isinstance(tokens, list) and len(tokens) >= 2:
        if isinstance(outcomes, list) and len(outcomes) >= 2:
            for idx, label in enumerate(outcomes[:2]):
                if str(label).lower() == "up":
                    up = str(tokens[idx])
                elif str(label).lower() == "down":
                    down = str(tokens[idx])
        if not up or not down:
            up, down = str(tokens[0]), str(tokens[1])
    if not up or not down:
        raise RuntimeError(f"Could not parse tokens for {slug}")
    condition_id = market.get("conditionId") or market.get("condition_id") or ""
    if not condition_id:
        raise RuntimeError(f"No condition id for {slug}")
    return Market(
        slug=slug,
        window_ts=window_ts,
        condition_id=str(condition_id),
        up_token_id=up,
        down_token_id=down,
        end_ts=window_ts + WINDOW_SECONDS,
    )


def geoblock_ok() -> dict[str, Any]:
    resp = requests.get("https://polymarket.com/api/geoblock", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("blocked") is True:
        raise RuntimeError(f"geoblock blocked: {data}")
    return data


def build_v1_client():
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds

    host = os.getenv("POLY_V1_HOST", "https://clob.polymarket.com")
    client = ClobClient(
        host=host,
        chain_id=int(os.getenv("POLY_CHAIN_ID", "137")),
        key=os.getenv("POLY_PRIVATE_KEY"),
        signature_type=int(os.getenv("POLY_SIGNATURE_TYPE", "1")),
        funder=os.getenv("POLY_FUNDER_ADDRESS"),
    )
    api_key = os.getenv("POLY_API_KEY") or os.getenv("POLY_CLOB_API_KEY")
    api_secret = os.getenv("POLY_SECRET") or os.getenv("POLY_CLOB_SECRET")
    api_passphrase = os.getenv("POLY_PASSPHRASE") or os.getenv("POLY_CLOB_PASSPHRASE")
    if api_key and api_secret and api_passphrase:
        creds = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_passphrase)
    elif hasattr(client, "create_or_derive_api_creds"):
        creds = client.create_or_derive_api_creds()
    else:
        creds = client.create_api_key(nonce=0)
    client.set_api_creds(creds)
    return client


def collateral_balance_micro(client: Any) -> int:
    from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

    params = BalanceAllowanceParams(
        asset_type=AssetType.COLLATERAL,
        signature_type=int(os.getenv("POLY_SIGNATURE_TYPE", "1")),
    )
    data = client.get_balance_allowance(params)
    return int(data.get("balance") or 0)


def post_gtc(client: Any, token_id: str, price: float, size_shares: float, neg_risk: bool) -> dict[str, Any]:
    from py_clob_client.clob_types import OrderArgs, OrderType, PartialCreateOrderOptions
    from py_clob_client.order_builder.constants import BUY

    order_args = OrderArgs(token_id=token_id, price=price, size=size_shares, side=BUY)
    options = PartialCreateOrderOptions(tick_size="0.01", neg_risk=neg_risk)
    signed = client.create_order(order_args, options=options)
    return client.post_order(signed, OrderType.GTC, post_only=True)


def model_probability(side: str, open_px: float, ref_px: float, seconds_remaining: float, sigma_intra: float, sigma_hourly: float) -> float:
    sigma = max(sigma_intra, sigma_hourly * 0.75, 1e-7)
    sigma_t = sigma * math.sqrt(max(1.0, seconds_remaining))
    z = math.log(max(open_px, 1e-12) / max(ref_px, 1e-12)) / max(sigma_t, 1e-7)
    p_down = normal_cdf(z)
    p_up = 1.0 - p_down
    if abs(math.log(max(ref_px, 1e-12) / max(open_px, 1e-12))) < sigma * 0.05:
        p_up = min(1.0, p_up + 0.0002)
        p_down = max(0.0, 1.0 - p_up)
    return clamp(p_up if side == "UP" else p_down, 0.0, 1.0)


def b_score(side: str, open_px: float, ref_px: float, seconds_remaining: float, sigma_intra: float, sigma_hourly: float, hour_return: float) -> float:
    time_factor = clamp(1.0 - seconds_remaining / WINDOW_SECONDS, 0.0, 1.0)
    vol_ratio = sigma_intra / max(sigma_hourly, 1e-7)
    vol_factor = 1.0 / (1.0 + math.exp(-1.8 * math.log(max(vol_ratio, 1e-9))))
    sigma = max(sigma_intra, sigma_hourly * 0.75, 1e-7)
    dist = abs(math.log(max(ref_px, 1e-12) / max(open_px, 1e-12)))
    denom = max(sigma * math.sqrt(max(seconds_remaining, 1.0)), 1e-7)
    pin_factor = math.exp(-dist / max(denom, 1e-12))
    momentum_factor = math.exp(-abs(hour_return) / 0.01)
    imbalance_factor = 0.5
    return clamp(
        0.28 * time_factor
        + 0.32 * vol_factor
        + 0.25 * pin_factor
        + 0.10 * momentum_factor
        + 0.05 * imbalance_factor,
        0.0,
        1.0,
    )


async def rtds_loop(state: ChainlinkState, log_path: Path, stop_event: asyncio.Event) -> None:
    sub = {
        "action": "subscribe",
        "subscriptions": [
            {
                "topic": "crypto_prices_chainlink",
                "type": "*",
                "filters": "",
            }
        ],
    }
    while not stop_event.is_set():
        try:
            async with websockets.connect(RTDS_URL, ping_interval=10, ping_timeout=20, max_size=2**23) as ws:
                await ws.send(json.dumps(sub))
                log_jsonl(log_path, {"event": "rtds_connected"})
                async def _app_ping() -> None:
                    while not stop_event.is_set():
                        await asyncio.sleep(10)
                        await ws.send("PING")

                ping_task = asyncio.create_task(_app_ping())
                async for raw in ws:
                    if stop_event.is_set():
                        break
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    items = payload if isinstance(payload, list) else [payload]
                    for item in items:
                        if isinstance(item, dict) and state.on_message(item):
                            log_jsonl(
                                log_path,
                                {
                                    "event": "chainlink_tick",
                                    "price": state.last_price,
                                    "event_ts": state.last_event_ts,
                                },
                            )
                ping_task.cancel()
                await asyncio.gather(ping_task, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log_jsonl(log_path, {"event": "rtds_error", "error": type(exc).__name__, "message": str(exc)[:300]})
            await asyncio.sleep(3)


async def probe_loop(args: argparse.Namespace) -> int:
    _load_env()
    if not os.getenv("POLY_PRIVATE_KEY") or not os.getenv("POLY_FUNDER_ADDRESS"):
        raise RuntimeError("Missing POLY_PRIVATE_KEY or POLY_FUNDER_ADDRESS")

    log_path = Path(args.log_jsonl)
    stop_event = asyncio.Event()
    state = ChainlinkState()

    def _stop(*_: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    geoblock = geoblock_ok()
    client = build_v1_client()
    balance = collateral_balance_micro(client)
    per_order_collateral = args.price * args.size_shares
    if balance < int(per_order_collateral * USDC_DECIMALS):
        raise RuntimeError("Insufficient collateral for one probe order")
    log_jsonl(
        log_path,
        {
            "event": "loop_start",
            "geoblock": geoblock,
            "collateral_balance_micro": balance,
            "order_price": args.price,
            "order_size_shares": args.size_shares,
            "per_order_collateral_units": per_order_collateral,
            "max_filled_collateral_units": args.max_filled_collateral_units,
        },
    )

    rtds_task = asyncio.create_task(rtds_loop(state, log_path, stop_event))
    open_order: Optional[OpenOrder] = None
    posted_keys: set[tuple[int, str]] = set()
    market_cache: dict[int, Market] = {}
    filled_collateral_units = 0.0
    last_decision_log = 0.0

    try:
        while not stop_event.is_set():
            now = time.time()
            window_ts = int(now // WINDOW_SECONDS) * WINDOW_SECONDS
            seconds_remaining = window_ts + WINDOW_SECONDS - now
            if window_ts not in market_cache:
                try:
                    market_cache[window_ts] = discover_market(window_ts)
                    log_jsonl(log_path, {"event": "market_discovered", **market_cache[window_ts].__dict__})
                except Exception as exc:
                    log_jsonl(log_path, {"event": "market_discovery_error", "error": type(exc).__name__, "message": str(exc)[:300]})
                    await asyncio.sleep(args.poll_seconds)
                    continue
            market = market_cache[window_ts]

            if open_order is not None:
                try:
                    order = client.get_order(open_order.order_id)
                    matched = float(order.get("size_matched") or 0.0)
                    if matched > open_order.filled_shares_seen:
                        delta = matched - open_order.filled_shares_seen
                        filled_collateral_units += delta * open_order.price
                        open_order.filled_shares_seen = matched
                        log_jsonl(
                            log_path,
                            {
                                "event": "fill_seen",
                                "order_id": open_order.order_id,
                                "side": open_order.side,
                                "matched_shares": matched,
                                "delta_shares": delta,
                                "filled_collateral_units": filled_collateral_units,
                                "order": order,
                            },
                        )
                    status = str(order.get("status") or "").upper()
                    if seconds_remaining <= args.cancel_at_t_minus_s and status not in {"CANCELED", "MATCHED", "FILLED"}:
                        cancel_resp = client.cancel(open_order.order_id)
                        log_jsonl(log_path, {"event": "cancel_sent", "order_id": open_order.order_id, "cancel_response": cancel_resp})
                        order = client.get_order(open_order.order_id)
                        log_jsonl(log_path, {"event": "post_cancel_check", "order_id": open_order.order_id, "order": order})
                        open_order = None
                    elif status in {"CANCELED", "MATCHED", "FILLED"}:
                        log_jsonl(log_path, {"event": "order_closed", "order_id": open_order.order_id, "order": order})
                        open_order = None
                except Exception as exc:
                    log_jsonl(log_path, {"event": "order_postcheck_error", "order_id": open_order.order_id, "error": type(exc).__name__, "message": str(exc)[:300]})

            if filled_collateral_units >= args.max_filled_collateral_units:
                log_jsonl(log_path, {"event": "daily_cap_reached", "filled_collateral_units": filled_collateral_units})
                await asyncio.sleep(args.poll_seconds)
                continue
            if open_order is not None:
                await asyncio.sleep(args.poll_seconds)
                continue
            if not (args.min_seconds_remaining <= seconds_remaining <= args.max_seconds_remaining):
                if now - last_decision_log > args.decision_log_interval:
                    log_jsonl(log_path, {"event": "no_signal", "reason": "time_window", "seconds_remaining": seconds_remaining})
                    last_decision_log = now
                await asyncio.sleep(args.poll_seconds)
                continue
            if state.last_price is None or state.last_arrival_ts is None or now - state.last_arrival_ts > args.max_chainlink_arrival_age_s:
                if now - last_decision_log > args.decision_log_interval:
                    log_jsonl(log_path, {"event": "no_signal", "reason": "chainlink_stale_or_missing"})
                    last_decision_log = now
                await asyncio.sleep(args.poll_seconds)
                continue
            open_px = state.open_for_window(window_ts)
            if open_px is None:
                if now - last_decision_log > args.decision_log_interval:
                    log_jsonl(log_path, {"event": "no_signal", "reason": "missing_window_open", "window_ts": window_ts})
                    last_decision_log = now
                await asyncio.sleep(args.poll_seconds)
                continue

            ref_px = float(state.last_price)
            if ref_px < open_px:
                side = "UP"
                token_id = market.up_token_id
            elif ref_px > open_px:
                side = "DOWN"
                token_id = market.down_token_id
            else:
                await asyncio.sleep(args.poll_seconds)
                continue
            key = (window_ts, side)
            if key in posted_keys:
                await asyncio.sleep(args.poll_seconds)
                continue

            sigma_intra = state.sigma_per_s(window_ts, args.default_sigma_intra_per_s)
            sigma_hourly = state.sigma_per_s(time.time() - 3600, args.default_sigma_hourly_per_s)
            prob = model_probability(side, open_px, ref_px, seconds_remaining, sigma_intra, sigma_hourly)
            score = b_score(side, open_px, ref_px, seconds_remaining, sigma_intra, sigma_hourly, state.hour_return())
            b_ratio = prob / args.price
            edge_abs = prob - args.price
            decision = {
                "event": "decision",
                "market_slug": market.slug,
                "condition_id": market.condition_id,
                "side": side,
                "token_id": token_id,
                "seconds_remaining": seconds_remaining,
                "open_price": open_px,
                "ref_price": ref_px,
                "sigma_intra_per_s": sigma_intra,
                "sigma_hourly_per_s": sigma_hourly,
                "model_prob": prob,
                "b_score": score,
                "b_ratio": b_ratio,
                "edge_abs": edge_abs,
            }
            gate_ok = (
                score >= args.min_b_score
                and b_ratio >= args.min_b_ratio
                and edge_abs >= args.min_abs_edge
                and prob <= args.max_model_prob_to_post
            )
            if not gate_ok:
                if now - last_decision_log > args.decision_log_interval:
                    decision["decision"] = "skip"
                    log_jsonl(log_path, decision)
                    last_decision_log = now
                await asyncio.sleep(args.poll_seconds)
                continue

            decision["decision"] = "post"
            log_jsonl(log_path, decision)
            try:
                response = post_gtc(client, token_id, args.price, args.size_shares, neg_risk=False)
                order_id = response.get("orderID") or response.get("id") or response.get("order_id")
                log_jsonl(log_path, {"event": "post_response", "response": response, "side": side, "market_slug": market.slug})
                posted_keys.add(key)
                if response.get("success") and order_id:
                    open_order = OpenOrder(
                        order_id=str(order_id),
                        market=market,
                        side=side,
                        token_id=token_id,
                        price=args.price,
                        size_shares=args.size_shares,
                        created_ts=now,
                    )
            except Exception as exc:
                log_jsonl(log_path, {"event": "post_error", "error": type(exc).__name__, "message": str(exc)[:500], "side": side, "market_slug": market.slug})
                posted_keys.add(key)

            await asyncio.sleep(args.poll_seconds)
    finally:
        if open_order is not None:
            try:
                cancel_resp = client.cancel(open_order.order_id)
                log_jsonl(log_path, {"event": "shutdown_cancel_sent", "order_id": open_order.order_id, "cancel_response": cancel_resp})
            except Exception as exc:
                log_jsonl(log_path, {"event": "shutdown_cancel_error", "order_id": open_order.order_id, "error": type(exc).__name__, "message": str(exc)[:300]})
        stop_event.set()
        rtds_task.cancel()
        await asyncio.gather(rtds_task, return_exceptions=True)
        log_jsonl(log_path, {"event": "loop_stop", "filled_collateral_units": filled_collateral_units})
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--price", type=float, default=0.01)
    parser.add_argument("--size-shares", type=float, default=5.0)
    parser.add_argument("--max-filled-collateral-units", type=float, default=3.0)
    parser.add_argument("--cancel-at-t-minus-s", type=float, default=6.0)
    parser.add_argument("--min-seconds-remaining", type=float, default=8.0)
    parser.add_argument("--max-seconds-remaining", type=float, default=280.0)
    parser.add_argument("--min-b-score", type=float, default=0.58)
    parser.add_argument("--min-b-ratio", type=float, default=1.15)
    parser.add_argument("--min-abs-edge", type=float, default=0.0015)
    parser.add_argument("--max-model-prob-to-post", type=float, default=0.35)
    parser.add_argument("--default-sigma-intra-per-s", type=float, default=0.00008)
    parser.add_argument("--default-sigma-hourly-per-s", type=float, default=0.00006)
    parser.add_argument("--max-chainlink-arrival-age-s", type=float, default=8.0)
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--decision-log-interval", type=float, default=15.0)
    parser.add_argument("--log-jsonl", default=str(PACKAGE_ROOT / "reports" / "v1_live_probe_loop.jsonl"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return asyncio.run(probe_loop(args))


if __name__ == "__main__":
    raise SystemExit(main())
