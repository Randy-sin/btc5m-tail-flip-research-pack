import unittest
from btc5m_tail_flip.core import Observation, TailFlipStrategy


class BFactorTests(unittest.TestCase):
    def test_b_score_increases_with_time_pressure_and_volatility(self):
        strat = TailFlipStrategy()
        early_low_vol = Observation("m", 10, 0, 300, "DOWN", 0.01, 100.0, 100.05, sigma_intraround_per_s=0.00004, sigma_hourly_per_s=0.00008)
        late_high_vol = Observation("m", 270, 0, 300, "DOWN", 0.01, 100.0, 100.05, sigma_intraround_per_s=0.00016, sigma_hourly_per_s=0.00008)
        b1 = strat.b_components(early_low_vol)["b_score"]
        b2 = strat.b_components(late_high_vol)["b_score"]
        self.assertGreater(b2, b1)

    def test_b_ratio_is_model_prob_over_break_even(self):
        strat = TailFlipStrategy()
        obs = Observation("m", 250, 0, 300, "DOWN", 0.02, 100.0, 100.05, sigma_intraround_per_s=0.0002, sigma_hourly_per_s=0.0001)
        ev = strat.evaluate(obs, "maker")
        self.assertAlmostEqual(ev["b_ratio"], ev["model_prob"] / ev["break_even"], places=12)


if __name__ == "__main__":
    unittest.main()
