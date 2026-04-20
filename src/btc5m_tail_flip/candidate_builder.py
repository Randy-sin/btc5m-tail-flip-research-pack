from __future__ import annotations

"""Normalize public HF data into strategy observations.

The BrockMisner daily slices contain orderbooks, trades, market resolutions and
minute BTC prices. They do not contain Chainlink intraround ticks. For a real-data
smoke test we therefore use:

- Gamma `eventMetadata.priceToBeat` as the Chainlink opening/settlement anchor.
- Brock resolution outcome as the ground-truth label.
- Brock BTC minute close as a reference/nowcast price, explicitly marked as a
  proxy in the output source field.
"""

import csv
import json
import math
import os
from bisect import bisect_right
from dataclasses import dataclass
from datetime import timezone
from typing import Dict, Iterable, List, Optional, Tuple

from .core import Observation
from .data_sources import gamma_market_by_slug
from .synthetic import FIELDS


@dataclass(frozen=True)
class GammaMarketMeta:
    slug: str
    price_to_beat: Optional[float]
    outcome: Optional[str]
    up_token_id: Optional[str]
    down_token_id: Optional[str]
    condition_id: Optional[str]


def epoch_seconds(value) -> int:
    try:
        import pandas as pd
    except Exception as e:  # pragma: no cover
        raise RuntimeError("pandas is required for HF candidate building") from e
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(timezone.utc)
    else:
        ts = ts.tz_convert(timezone.utc)
    return int(ts.timestamp())


def parse_window_start(market_id: str) -> int:
    return int(str(market_id).rsplit("-", 1)[-1])


def _load_json(path: str) -> Dict[str, object]:
    if not path or not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _write_json(path: str, data: Dict[str, object]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def _token_ids_from_gamma(raw: Dict[str, object]) -> Tuple[Optional[str], Optional[str]]:
    outcomes = raw.get("outcomes")
    tokens = raw.get("clobTokenIds") or raw.get("clob_token_ids")
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
    if not isinstance(outcomes, list) or not isinstance(tokens, list):
        return None, None
    mapping = {str(o).upper(): str(t) for o, t in zip(outcomes, tokens)}
    return mapping.get("UP"), mapping.get("DOWN")


def gamma_meta_from_raw(slug: str, raw: Dict[str, object]) -> GammaMarketMeta:
    event_meta = {}
    events = raw.get("events")
    if isinstance(events, list) and events:
        event_meta = events[0].get("eventMetadata") or {}
    price_to_beat = event_meta.get("priceToBeat")
    if price_to_beat is None:
        price_to_beat = raw.get("priceToBeat")
    up_token_id, down_token_id = _token_ids_from_gamma(raw)
    outcome = None
    outcome_prices = raw.get("outcomePrices")
    outcomes = raw.get("outcomes")
    if isinstance(outcome_prices, str) and isinstance(outcomes, str):
        try:
            prices = json.loads(outcome_prices)
            outs = json.loads(outcomes)
            for out, price in zip(outs, prices):
                if float(price) >= 0.999:
                    outcome = str(out)
                    break
        except Exception:
            outcome = None
    return GammaMarketMeta(
        slug=slug,
        price_to_beat=float(price_to_beat) if price_to_beat is not None else None,
        outcome=outcome,
        up_token_id=up_token_id,
        down_token_id=down_token_id,
        condition_id=str(raw.get("conditionId")) if raw.get("conditionId") else None,
    )


def fetch_gamma_meta(slug: str, cache_path: Optional[str] = None, refresh: bool = False) -> GammaMarketMeta:
    cache = _load_json(cache_path) if cache_path else {}
    if not refresh and slug in cache:
        return GammaMarketMeta(**cache[slug])  # type: ignore[arg-type]
    raw = gamma_market_by_slug(slug)
    meta = gamma_meta_from_raw(slug, raw)
    if cache_path:
        cache[slug] = meta.__dict__
        _write_json(cache_path, cache)
    return meta


def load_aliplayer_token_map(markets_path: str) -> Dict[str, Tuple[str, str]]:
    try:
        import pandas as pd
    except Exception as e:  # pragma: no cover
        raise RuntimeError("pandas is required for parquet token map loading") from e
    cols = ["condition_id", "up_token_id", "down_token_id", "crypto", "timeframe"]
    df = pd.read_parquet(markets_path, columns=cols)
    df = df[(df["crypto"] == "BTC") & (df["timeframe"] == "5-minute")]
    return {
        str(r.condition_id): (str(r.up_token_id), str(r.down_token_id))
        for r in df.itertuples(index=False)
    }


def _levels_size_at(levels_json: object, price: float) -> float:
    if levels_json in (None, ""):
        return 0.0
    if isinstance(levels_json, str):
        try:
            levels = json.loads(levels_json)
        except Exception:
            return 0.0
    else:
        levels = levels_json
    total = 0.0
    for level in levels or []:
        try:
            if abs(float(level.get("price")) - price) < 1e-9:
                total += float(level.get("size", 0.0))
        except Exception:
            continue
    return total


def _depth_top(levels_json: object, n: int = 5) -> float:
    if levels_json in (None, ""):
        return 0.0
    if isinstance(levels_json, str):
        try:
            levels = json.loads(levels_json)
        except Exception:
            return 0.0
    else:
        levels = levels_json
    total = 0.0
    for level in list(levels or [])[:n]:
        try:
            total += float(level.get("size", 0.0))
        except Exception:
            continue
    return total


def _prepare_price_points(crypto_prices_path: str) -> List[Dict[str, float]]:
    try:
        import pandas as pd
    except Exception as e:  # pragma: no cover
        raise RuntimeError("pandas is required for price point loading") from e
    df = pd.read_parquet(crypto_prices_path)
    df = df[df["asset"] == "BTC"].sort_values("timestamp").copy()
    df["epoch"] = df["timestamp"].map(epoch_seconds)
    df["log_close"] = df["close"].map(lambda x: math.log(float(x)))
    df["log_ret"] = df["log_close"].diff()
    df["sigma_intraround_per_s"] = df["log_ret"].rolling(5, min_periods=2).std().fillna(0.00008) / math.sqrt(60.0)
    df["sigma_hourly_per_s"] = df["log_ret"].rolling(60, min_periods=5).std().fillna(0.00006) / math.sqrt(60.0)
    df["hour_return"] = (df["log_close"] - df["log_close"].shift(60)).fillna(0.0)
    return [
        {
            "epoch": int(r.epoch),
            "close": float(r.close),
            "sigma_intraround_per_s": max(float(r.sigma_intraround_per_s), 1e-7),
            "sigma_hourly_per_s": max(float(r.sigma_hourly_per_s), 1e-7),
            "hour_return": float(r.hour_return),
        }
        for r in df.itertuples(index=False)
    ]


def _nearest_price_before(points: List[Dict[str, float]], ts: int) -> Optional[Dict[str, float]]:
    epochs = [int(p["epoch"]) for p in points]
    idx = bisect_right(epochs, ts) - 1
    if idx < 0:
        return None
    return points[idx]


def _settlement_close_from_outcome(open_price: float, outcome: str) -> float:
    return open_price * (1.000001 if outcome.upper() == "UP" else 0.999999)


def build_candidates_from_brock(
    orderbooks_path: str,
    crypto_prices_path: str,
    resolutions_path: str,
    aliplayer_markets_path: str,
    out_csv: str,
    gamma_cache_path: Optional[str] = None,
    fetch_gamma: bool = False,
    max_seconds_remaining: int = 120,
    min_seconds_remaining: int = 8,
) -> int:
    try:
        import pandas as pd
    except Exception as e:  # pragma: no cover
        raise RuntimeError("pandas is required for candidate building") from e

    token_map = load_aliplayer_token_map(aliplayer_markets_path)
    price_points = _prepare_price_points(crypto_prices_path)
    resolutions = pd.read_parquet(resolutions_path)
    resolutions = resolutions[(resolutions["asset"] == "BTC") & (resolutions["market_id"].astype(str).str.contains("5m"))]
    outcome_by_market = {str(r.market_id): str(r.outcome) for r in resolutions.itertuples(index=False)}

    orderbooks = pd.read_parquet(orderbooks_path)
    orderbooks = orderbooks[(orderbooks["asset"] == "BTC") & (orderbooks["market_id"].astype(str).str.contains("5m"))].copy()
    orderbooks["epoch"] = orderbooks["timestamp"].map(epoch_seconds)
    orderbooks["window_start_ts"] = orderbooks["market_id"].map(parse_window_start)
    orderbooks["window_end_ts"] = orderbooks["window_start_ts"] + 300
    orderbooks["seconds_remaining"] = orderbooks["window_end_ts"] - orderbooks["epoch"]
    orderbooks = orderbooks[
        (orderbooks["seconds_remaining"] >= min_seconds_remaining)
        & (orderbooks["seconds_remaining"] <= max_seconds_remaining)
        & (orderbooks["best_bid"].isin([0.01, 0.02]))
    ].sort_values("epoch")

    rows: List[Observation] = []
    extra_rows: List[Dict[str, object]] = []
    gamma_by_slug: Dict[str, GammaMarketMeta] = {}

    for r in orderbooks.itertuples(index=False):
        cond = str(r.condition_id)
        if cond not in token_map:
            continue
        up_token, down_token = token_map[cond]
        token_id = str(r.token_id)
        if token_id == up_token:
            side = "UP"
        elif token_id == down_token:
            side = "DOWN"
        else:
            continue
        market_id = str(r.market_id)
        outcome = outcome_by_market.get(market_id)
        if outcome not in {"Up", "Down", "UP", "DOWN"}:
            continue
        price_point = _nearest_price_before(price_points, int(r.epoch))
        if not price_point:
            continue

        price_to_beat: Optional[float] = None
        if fetch_gamma:
            if market_id not in gamma_by_slug:
                gamma_by_slug[market_id] = fetch_gamma_meta(market_id, cache_path=gamma_cache_path)
            price_to_beat = gamma_by_slug[market_id].price_to_beat
        if price_to_beat is None:
            start_price_point = _nearest_price_before(price_points, int(r.window_start_ts))
            price_to_beat = float(start_price_point["close"]) if start_price_point else float(price_point["close"])

        bid_depth_1 = _levels_size_at(r.bid_levels, float(r.best_bid))
        ask_depth_1 = _levels_size_at(r.ask_levels, float(r.best_ask))
        bid_depth_5 = _depth_top(r.bid_levels, n=5)
        ask_depth_5 = _depth_top(r.ask_levels, n=5)
        denom = bid_depth_5 + ask_depth_5
        imbalance = (bid_depth_5 - ask_depth_5) / denom if denom > 0 else 0.0

        obs = Observation(
            market_id=market_id,
            ts=int(r.epoch),
            window_start_ts=int(r.window_start_ts),
            window_end_ts=int(r.window_end_ts),
            side=side,
            token_price=float(r.best_bid),
            chainlink_open_price=float(price_to_beat),
            chainlink_ref_price=float(price_point["close"]),
            chainlink_close_price=_settlement_close_from_outcome(float(price_to_beat), outcome),
            binance_mid_price=float(price_point["close"]),
            sigma_intraround_per_s=float(price_point["sigma_intraround_per_s"]),
            sigma_hourly_per_s=float(price_point["sigma_hourly_per_s"]),
            hour_return=float(price_point["hour_return"]),
            orderbook_imbalance=float(max(-1.0, min(1.0, imbalance))),
            bid_depth_1=bid_depth_1,
            ask_depth_1=ask_depth_1,
            source="hf_brock_public_smoke:binance_ref:gamma_price_to_beat:resolution_label",
        )
        rows.append(obs)
        extra_rows.append({
            "condition_id": cond,
            "token_id": token_id,
            "settled_side": outcome.upper(),
            "queue_ahead": bid_depth_1,
            "best_ask": float(r.best_ask),
        })

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    fields = FIELDS + ["condition_id", "token_id", "settled_side", "queue_ahead", "best_ask"]
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for obs, extra in zip(rows, extra_rows):
            row = {field: getattr(obs, field) for field in FIELDS}
            row.update(extra)
            writer.writerow(row)
    return len(rows)
