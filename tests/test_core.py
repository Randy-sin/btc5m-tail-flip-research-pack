import math
import unittest

from btc5m_tail_flip.core import (
    Observation, StrategyConfig, TailFlipStrategy, taker_fee_per_share,
    break_even_cost, kelly_fraction_for_binary
)


class CoreMathTests(unittest.TestCase):
    def test_taker_fee_formula_crypto(self):
        self.assertAlmostEqual(taker_fee_per_share(0.50), 0.018, places=9)
        self.assertAlmostEqual(taker_fee_per_share(0.01), 0.0007128, places=9)
        self.assertAlmostEqual(break_even_cost(0.02, "fok"), 0.0214112, places=9)
        self.assertAlmostEqual(break_even_cost(0.02, "maker"), 0.02, places=9)

    def test_kelly_binary(self):
        k = kelly_fraction_for_binary(0.0121, 0.01, multiplier=0.25)
        self.assertGreater(k, 0)
        self.assertLess(k, 0.001)
        self.assertEqual(kelly_fraction_for_binary(0.005, 0.01, multiplier=0.25), 0.0)

    def test_model_probability_symmetry_near_strike(self):
        obs_up = Observation("m", 100, 0, 130, "UP", 0.01, 100.0, 100.0, sigma_intraround_per_s=0.0001, sigma_hourly_per_s=0.0001)
        strat = TailFlipStrategy()
        p_up = strat.model_win_probability(obs_up)
        obs_down = Observation("m", 100, 0, 130, "DOWN", 0.01, 100.0, 100.0, sigma_intraround_per_s=0.0001, sigma_hourly_per_s=0.0001)
        p_down = strat.model_win_probability(obs_down)
        self.assertGreater(p_up, p_down)  # tie rule tiny bias to UP
        self.assertAlmostEqual(p_up + p_down, 1.0, places=9)

    def test_evaluate_1c_trade_when_model_edge_high(self):
        # Ref is below open; UP is the 1c tail but close enough / volatile enough to be positive EV.
        obs = Observation(
            market_id="m", ts=270, window_start_ts=0, window_end_ts=300,
            side="UP", token_price=0.01, chainlink_open_price=100.0, chainlink_ref_price=99.97,
            sigma_intraround_per_s=0.00018, sigma_hourly_per_s=0.00007, hour_return=0.0,
        )
        ev = TailFlipStrategy().evaluate(obs, "maker")
        self.assertTrue(ev["trade"], ev)
        self.assertGreater(ev["model_prob"], ev["break_even"])
        self.assertGreaterEqual(ev["b_ratio"], 1.15)

    def test_evaluate_rejects_too_late(self):
        obs = Observation(
            market_id="m", ts=297, window_start_ts=0, window_end_ts=300,
            side="UP", token_price=0.01, chainlink_open_price=100.0, chainlink_ref_price=99.99,
            sigma_intraround_per_s=0.001, sigma_hourly_per_s=0.0001,
        )
        ev = TailFlipStrategy().evaluate(obs, "maker")
        self.assertFalse(ev["trade"])
        self.assertIn("too_late", ev["reason"])


if __name__ == "__main__":
    unittest.main()
