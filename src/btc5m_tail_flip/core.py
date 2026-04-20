from __future__ import annotations

from dataclasses import dataclass, asdict
import math
from typing import Dict, Optional

CRYPTO_TAKER_FEE_RATE = 0.072


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def taker_fee_per_share(price: float, fee_rate: float = CRYPTO_TAKER_FEE_RATE) -> float:
    """Polymarket fee formula per share: fee = C * feeRate * p * (1-p), C=1."""
    if price < 0 or price > 1:
        raise ValueError("price must be in [0, 1]")
    return fee_rate * price * (1.0 - price)


def break_even_cost(price: float, order_type: str = "maker", fee_rate: float = CRYPTO_TAKER_FEE_RATE) -> float:
    """All-in cost/probability needed to break even for $1 payout binary share."""
    order_type = order_type.lower()
    if order_type in {"maker", "gtc", "gtd", "post_only"}:
        return price
    if order_type in {"taker", "fok", "fak", "market"}:
        return price + taker_fee_per_share(price, fee_rate=fee_rate)
    raise ValueError(f"unknown order_type={order_type}")


def roi_per_filled_dollar(win_prob: float, all_in_cost: float) -> float:
    """Expected ROI on dollars spent. Binary share pays $1 with probability win_prob."""
    if all_in_cost <= 0:
        raise ValueError("cost must be positive")
    return win_prob / all_in_cost - 1.0


def kelly_fraction_for_binary(win_prob: float, all_in_cost: float, multiplier: float = 0.25) -> float:
    """Kelly fraction for a binary share costing all_in_cost and paying $1 if it wins.

    Full Kelly for this payoff is (p - c) / (1-c); this returns clipped multiplier Kelly.
    """
    if all_in_cost <= 0 or all_in_cost >= 1:
        return 0.0
    full = (win_prob - all_in_cost) / (1.0 - all_in_cost)
    return max(0.0, full * multiplier)


@dataclass(frozen=True)
class Observation:
    market_id: str
    ts: int
    window_start_ts: int
    window_end_ts: int
    side: str  # UP or DOWN
    token_price: float
    chainlink_open_price: float
    chainlink_ref_price: float
    chainlink_close_price: Optional[float] = None
    binance_mid_price: Optional[float] = None
    sigma_intraround_per_s: float = 0.00008
    sigma_hourly_per_s: float = 0.00006
    hour_return: float = 0.0
    orderbook_imbalance: float = 0.0
    bid_depth_1: float = 0.0
    ask_depth_1: float = 0.0
    source: str = "fixture"

    @property
    def seconds_remaining(self) -> float:
        return max(0.0, float(self.window_end_ts - self.ts))

    @property
    def result_win(self) -> Optional[bool]:
        if self.chainlink_close_price is None:
            return None
        side = self.side.upper()
        if side == "UP":
            return self.chainlink_close_price >= self.chainlink_open_price
        if side == "DOWN":
            return self.chainlink_close_price < self.chainlink_open_price
        raise ValueError("side must be UP or DOWN")

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        d["seconds_remaining"] = self.seconds_remaining
        d["result_win"] = self.result_win
        return d


@dataclass(frozen=True)
class StrategyConfig:
    min_time_remaining_s: float = 8.0
    max_time_remaining_s: float = 120.0
    cancel_time_remaining_s: float = 6.0
    max_tail_price_maker: float = 0.02
    allow_fok: bool = False
    min_b_ratio: float = 1.15
    min_abs_edge_maker_1c: float = 0.0015
    min_abs_edge_maker_2c: float = 0.0035
    min_abs_edge_fok_2c: float = 0.0060
    quarter_kelly_multiplier: float = 0.25
    max_single_trade_pct: float = 0.0005
    max_window_risk_pct: float = 0.0010
    sigma_floor_per_s: float = 1e-7


class TailFlipStrategy:
    """Tail-flip strategy from the article: price-structure first, direction second.

    It evaluates whether a 1c/2c tail token is mathematically underpriced relative
    to a Chainlink-anchored terminal probability estimate.
    """

    def __init__(self, config: StrategyConfig | None = None):
        self.config = config or StrategyConfig()

    def model_win_probability(self, obs: Observation) -> float:
        side = obs.side.upper()
        t = max(0.0, obs.seconds_remaining)
        if t <= 0:
            if side == "UP":
                return 1.0 if obs.chainlink_ref_price >= obs.chainlink_open_price else 0.0
            return 1.0 if obs.chainlink_ref_price < obs.chainlink_open_price else 0.0

        ref = max(obs.chainlink_ref_price, 1e-12)
        strike = max(obs.chainlink_open_price, 1e-12)
        sigma = max(obs.sigma_intraround_per_s, obs.sigma_hourly_per_s * 0.75, self.config.sigma_floor_per_s)
        sigma_t = sigma * math.sqrt(t)
        z = math.log(strike / ref) / max(sigma_t, self.config.sigma_floor_per_s)
        p_down = normal_cdf(z)
        p_up = 1.0 - p_down

        # BTC 5m tie rule is UP wins. In a continuous model ties have zero mass; this
        # tiny bias prevents exact-at-strike observations from penalizing UP.
        if abs(math.log(ref / strike)) < sigma * 0.05:
            p_up = min(1.0, p_up + 0.0002)
            p_down = max(0.0, 1.0 - p_up)

        return clamp(p_up if side == "UP" else p_down, 0.0, 1.0)

    def b_components(self, obs: Observation, model_prob: Optional[float] = None) -> Dict[str, float]:
        t = obs.seconds_remaining
        time_factor = clamp(1.0 - t / 300.0, 0.0, 1.0)

        vol_ratio = obs.sigma_intraround_per_s / max(obs.sigma_hourly_per_s, self.config.sigma_floor_per_s)
        # Smoothly map vol ratio: 1 => 0.5, >1 higher, <1 lower.
        vol_factor = 1.0 / (1.0 + math.exp(-1.8 * math.log(max(vol_ratio, 1e-9))))

        # Pin factor: high when reference price is close enough to open relative to remaining volatility.
        sigma = max(obs.sigma_intraround_per_s, obs.sigma_hourly_per_s * 0.75, self.config.sigma_floor_per_s)
        dist = abs(math.log(max(obs.chainlink_ref_price, 1e-12) / max(obs.chainlink_open_price, 1e-12)))
        denom = max(sigma * math.sqrt(max(t, 1.0)), self.config.sigma_floor_per_s)
        pin_factor = math.exp(-dist / max(denom, 1e-12))

        # Mean-reversion bonus: strong 1h trend lowers flip quality; flat market raises it.
        momentum_factor = math.exp(-abs(obs.hour_return) / 0.01)

        imbalance_factor = (obs.orderbook_imbalance + 1.0) / 2.0
        if obs.side.upper() == "DOWN":
            imbalance_factor = 1.0 - imbalance_factor
        imbalance_factor = clamp(imbalance_factor, 0.0, 1.0)

        b_score = (
            0.28 * time_factor
            + 0.32 * vol_factor
            + 0.25 * pin_factor
            + 0.10 * momentum_factor
            + 0.05 * imbalance_factor
        )
        return {
            "time_factor": time_factor,
            "vol_factor": vol_factor,
            "pin_factor": pin_factor,
            "momentum_factor": momentum_factor,
            "imbalance_factor": imbalance_factor,
            "b_score": clamp(b_score, 0.0, 1.0),
        }

    def evaluate(self, obs: Observation, order_type: str = "maker") -> Dict[str, object]:
        cfg = self.config
        model_prob = self.model_win_probability(obs)
        cost = break_even_cost(obs.token_price, order_type=order_type)
        b_ratio = model_prob / cost if cost > 0 else 0.0
        edge_abs = model_prob - cost
        comps = self.b_components(obs, model_prob=model_prob)
        price_cents = round(obs.token_price * 100)

        reason = []
        trade = True
        if obs.seconds_remaining < cfg.min_time_remaining_s:
            trade = False; reason.append("too_late")
        if obs.seconds_remaining > cfg.max_time_remaining_s:
            trade = False; reason.append("too_early")
        if obs.token_price > cfg.max_tail_price_maker and not (order_type.lower() in {"fok", "taker"} and obs.token_price <= 0.02):
            trade = False; reason.append("not_tail_price")
        if b_ratio < cfg.min_b_ratio:
            trade = False; reason.append("b_ratio_below_threshold")

        if order_type.lower() in {"maker", "gtc", "gtd", "post_only"}:
            if price_cents <= 1 and edge_abs < cfg.min_abs_edge_maker_1c:
                trade = False; reason.append("edge_1c_below_threshold")
            if price_cents == 2 and edge_abs < cfg.min_abs_edge_maker_2c:
                trade = False; reason.append("edge_2c_below_threshold")
        else:
            if not cfg.allow_fok:
                trade = False; reason.append("fok_disabled")
            if price_cents == 2 and edge_abs < cfg.min_abs_edge_fok_2c:
                trade = False; reason.append("edge_fok_2c_below_threshold")

        return {
            "trade": bool(trade),
            "reason": ",".join(reason) if reason else "ok",
            "model_prob": model_prob,
            "break_even": cost,
            "b_ratio": b_ratio,
            "edge_abs": edge_abs,
            "b_score": comps["b_score"],
            **comps,
            "ev_roi": roi_per_filled_dollar(model_prob, cost) if cost > 0 else 0.0,
        }

    def size_order(self, bankroll: float, obs: Observation, order_type: str = "maker") -> Dict[str, float]:
        ev = self.evaluate(obs, order_type=order_type)
        cost = float(ev["break_even"])
        kelly = kelly_fraction_for_binary(float(ev["model_prob"]), cost, self.config.quarter_kelly_multiplier)
        dollar_risk = bankroll * min(kelly, self.config.max_single_trade_pct)
        max_window = bankroll * self.config.max_window_risk_pct
        dollar_risk = min(dollar_risk, max_window)
        shares = dollar_risk / max(cost, 1e-12)
        return {
            "bankroll": bankroll,
            "dollar_risk": dollar_risk,
            "shares": shares,
            "kelly_fraction": kelly,
            "cost_per_share": cost,
        }
