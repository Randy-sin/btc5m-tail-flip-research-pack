from __future__ import annotations

"""Public data source adapters.

These adapters are intentionally not used in unit tests because the sandbox may not
have internet access. They are included so the same research package can be run on
an internet-connected server to collect real BTC 5m Polymarket/Chainlink data.
"""

import csv
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlencode

try:
    import requests
except Exception:  # pragma: no cover
    requests = None  # type: ignore

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
RTDS_WS = "wss://ws-live-data.polymarket.com"
CLOB_MARKET_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
PUBLIC_SNAPSHOT_REPO_RAW_BASE = "https://github.com/CronosVirus00/polymarket-BTC5min-database/raw/refs/heads/main/market_data"


def require_requests():
    if requests is None:
        raise RuntimeError("requests is not installed. pip install requests")
    return requests


def btc5m_slug_for_ts(ts: Optional[int] = None) -> str:
    ts = int(time.time()) if ts is None else int(ts)
    window = ts // 300 * 300
    return f"btc-updown-5m-{window}"


def gamma_market_by_slug(slug: str, timeout: float = 15.0) -> Dict[str, Any]:
    req = require_requests()
    url = f"{GAMMA_BASE}/markets/slug/{slug}"
    r = req.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def extract_token_ids(market_json: Dict[str, Any]) -> Dict[str, str]:
    outcomes = market_json.get("outcomes")
    tokens = market_json.get("clobTokenIds") or market_json.get("clob_token_ids")
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except Exception:
            outcomes = []
    if isinstance(tokens, str):
        try:
            tokens = json.loads(tokens)
        except Exception:
            tokens = []
    if not outcomes or not tokens:
        return {}
    return {str(o).upper(): str(t) for o, t in zip(outcomes, tokens)}


def clob_prices_history(token_id: str, start_ts: Optional[int] = None, end_ts: Optional[int] = None, interval: str = "1m", fidelity: int = 1, timeout: float = 20.0) -> Dict[str, Any]:
    req = require_requests()
    params: Dict[str, Any] = {"market": token_id, "interval": interval, "fidelity": fidelity}
    if start_ts is not None:
        params["startTs"] = int(start_ts)
    if end_ts is not None:
        params["endTs"] = int(end_ts)
    url = f"{CLOB_BASE}/prices-history?{urlencode(params)}"
    r = req.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def clob_orderbook_history_best_effort(token_id: str, start_ms: int, end_ms: int, limit: int = 500, offset: int = 0, timeout: float = 30.0) -> Dict[str, Any]:
    """Undocumented endpoint; known to be unreliable after Feb 2026.

    Kept as a best-effort adapter so failures are explicit rather than hidden.
    """
    req = require_requests()
    params = {"asset_id": token_id, "startTs": start_ms, "endTs": end_ms, "limit": limit, "offset": offset}
    r = req.get(f"{CLOB_BASE}/orderbook-history", params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def public_snapshot_raw_url(filename: str) -> str:
    if "/" in filename or not filename.endswith(".parquet"):
        raise ValueError("filename must be a single parquet file name")
    return f"{PUBLIC_SNAPSHOT_REPO_RAW_BASE}/{filename}"


def write_market_manifest(slugs: Iterable[str], path: str) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["slug", "window_start_ts"])
        w.writeheader()
        for slug in slugs:
            w.writerow({"slug": slug, "window_start_ts": slug.rsplit("-", 1)[-1]})
