from __future__ import annotations

import csv
import math
import random
from typing import List

from .core import Observation


FIELDS = [
    "market_id", "ts", "window_start_ts", "window_end_ts", "side", "token_price",
    "chainlink_open_price", "chainlink_ref_price", "chainlink_close_price", "binance_mid_price",
    "sigma_intraround_per_s", "sigma_hourly_per_s", "hour_return", "orderbook_imbalance",
    "bid_depth_1", "ask_depth_1", "source"
]


def generate_fixture_observations(n_markets: int = 160, seed: int = 42) -> List[Observation]:
    """Generate deterministic, non-real BTC5m observations for tests.

    The fixture deliberately includes 1c/2c tails, some true flips, and many no-trade
    rows so that B-factor calibration and edge-gating can be regression tested.
    """
    rng = random.Random(seed)
    base_ts = 1776323400
    btc = 86500.0
    obs: List[Observation] = []
    for i in range(n_markets):
        start = base_ts + 300 * i
        end = start + 300
        open_px = btc * (1.0 + rng.gauss(0, 0.0004))
        # Most windows close in the direction implied at T-30; some are tail flips.
        is_tail_flip = (i % 23 == 0) or (i % 41 == 0)
        normal_dir = 1 if rng.random() > 0.5 else -1
        if is_tail_flip:
            # At observation time the market has moved opposite, but close flips across open.
            early_dir = normal_dir
            close_dir = -normal_dir
            magnitude = rng.uniform(0.00005, 0.00028)
            close_px = open_px * (1.0 + close_dir * magnitude)
        else:
            early_dir = normal_dir
            magnitude = rng.uniform(0.00012, 0.0012)
            close_px = open_px * (1.0 + early_dir * magnitude)
        sigma_h = rng.uniform(0.000045, 0.000090)
        sigma_i = sigma_h * rng.uniform(0.8, 2.4 if is_tail_flip else 1.6)
        hour_ret = rng.gauss(0, 0.003 if is_tail_flip else 0.008)

        for sec_rem in [120, 90, 60, 30, 15, 10]:
            ts = end - sec_rem
            # Reference price between open and early move; tail flips move back near the strike late.
            if is_tail_flip:
                early_distance = early_dir * rng.uniform(0.00016, 0.00045)
                pin_pull = (120 - sec_rem) / 120.0 * rng.uniform(0.45, 0.9)
                ref_px = open_px * (1.0 + early_distance * (1 - pin_pull) + rng.gauss(0, 0.00003))
            else:
                ref_px = open_px * (1.0 + early_dir * magnitude * (1 - sec_rem / 350.0) + rng.gauss(0, 0.00005))
            binance = ref_px * (1.0 + rng.gauss(0, 0.00003))
            # If ref above open, DOWN is tail; if below, UP is tail.
            tail_side = "DOWN" if ref_px >= open_px else "UP"
            fav_side = "UP" if tail_side == "DOWN" else "DOWN"
            tail_price = 0.01 if sec_rem <= 60 and (abs(math.log(ref_px / open_px)) > 0.00005 or is_tail_flip) else 0.02
            if sec_rem > 90:
                tail_price = 0.03
            if is_tail_flip and sec_rem <= 60:
                tail_price = 0.01 if i % 2 == 0 else 0.02
            fav_price = max(0.70, min(0.99, 1.0 - tail_price))
            # Add only tail rows and a few favorite/no-trade rows.
            for side, price in [(tail_side, tail_price), (fav_side, fav_price)]:
                if price > 0.05 and i % 7 != 0:
                    continue
                imbalance = rng.uniform(-0.5, 0.5)
                if side == "UP":
                    imbalance += 0.1
                else:
                    imbalance -= 0.1
                obs.append(Observation(
                    market_id=f"btc-updown-5m-{start}",
                    ts=ts,
                    window_start_ts=start,
                    window_end_ts=end,
                    side=side,
                    token_price=price,
                    chainlink_open_price=open_px,
                    chainlink_ref_price=ref_px,
                    chainlink_close_price=close_px,
                    binance_mid_price=binance,
                    sigma_intraround_per_s=sigma_i,
                    sigma_hourly_per_s=sigma_h,
                    hour_return=hour_ret,
                    orderbook_imbalance=max(-1.0, min(1.0, imbalance)),
                    bid_depth_1=rng.uniform(20, 500),
                    ask_depth_1=rng.uniform(20, 500),
                    source="synthetic_fixture_not_real_history",
                ))
        btc = close_px
    return obs


def write_fixture_csv(path: str, n_markets: int = 160, seed: int = 42) -> int:
    rows = generate_fixture_observations(n_markets=n_markets, seed=seed)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for o in rows:
            writer.writerow({field: getattr(o, field) for field in FIELDS})
    return len(rows)
