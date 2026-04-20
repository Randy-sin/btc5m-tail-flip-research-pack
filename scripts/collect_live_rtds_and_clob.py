#!/usr/bin/env python3
"""Skeleton collector for real-time Polymarket RTDS + CLOB market stream.

Run this on an internet-connected machine. It writes raw JSONL; a normalizer should
convert raw events into the schema in docs/DATA_SCHEMA.md before backtesting.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from btc5m_tail_flip.data_sources import RTDS_WS, CLOB_MARKET_WS


async def consume(ws_url: str, subscribe_message: dict, out_path: str, stop: asyncio.Event):
    try:
        import websockets
    except Exception as e:
        raise RuntimeError("pip install websockets to use the collector") from e
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    async with websockets.connect(ws_url, ping_interval=10, ping_timeout=20) as ws:
        await ws.send(json.dumps(subscribe_message))
        with open(out_path, "a") as f:
            while not stop.is_set():
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                f.write(json.dumps({"arrival_ts_ns": time.time_ns(), "raw": msg}, ensure_ascii=False) + "\n")
                f.flush()


async def main_async(args) -> int:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    tasks = []
    if args.rtds:
        sub = {"action": "subscribe", "subscriptions": [
            {"topic": "crypto_prices_chainlink", "type": "*", "filters": ""},
            {"topic": "crypto_prices", "type": "update", "filters": "btcusdt"},
        ]}
        tasks.append(asyncio.create_task(consume(RTDS_WS, sub, os.path.join(args.out_dir, "rtds.jsonl"), stop)))
    if args.tokens:
        sub = {"assets_ids": args.tokens.split(","), "type": "market", "custom_feature_enabled": True}
        tasks.append(asyncio.create_task(consume(CLOB_MARKET_WS, sub, os.path.join(args.out_dir, "clob_market.jsonl"), stop)))
    if not tasks:
        print("Nothing to collect. Pass --rtds and/or --tokens TOKEN1,TOKEN2")
        return 2
    await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    stop.set()
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rtds", action="store_true", help="collect Chainlink/Binance RTDS")
    p.add_argument("--tokens", help="comma-separated CLOB token IDs for market channel")
    p.add_argument("--out-dir", default="data/raw_live")
    args = p.parse_args()
    args.out_dir = args.out_dir if os.path.isabs(args.out_dir) else os.path.join(ROOT, args.out_dir)
    return asyncio.run(main_async(args))

if __name__ == "__main__":
    raise SystemExit(main())
