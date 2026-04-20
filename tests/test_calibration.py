import unittest
from btc5m_tail_flip.calibration import wilson_interval, posterior_prob_edge_positive, assign_deciles, aggregate_calibration


class CalibrationTests(unittest.TestCase):
    def test_wilson_interval_bounds(self):
        lo, hi = wilson_interval(5, 100)
        self.assertGreaterEqual(lo, 0.0)
        self.assertLessEqual(hi, 1.0)
        self.assertLess(lo, 0.05)
        self.assertGreater(hi, 0.05)

    def test_posterior_prob_edge_positive(self):
        high = posterior_prob_edge_positive(6, 294, 0.01)
        low = posterior_prob_edge_positive(1, 299, 0.01)
        self.assertGreater(high, low)
        self.assertGreater(high, 0.5)

    def test_deciles_length_and_range(self):
        dec = assign_deciles([0.1, 0.2, 0.3, 0.4, 0.5])
        self.assertEqual(len(dec), 5)
        self.assertTrue(all(0 <= d <= 9 for d in dec))

    def test_aggregate_calibration(self):
        rows = [
            {"price_b_decile": "1c:B9", "trade": True, "result_win": True, "break_even": 0.01},
            {"price_b_decile": "1c:B9", "trade": True, "result_win": False, "break_even": 0.01},
            {"price_b_decile": "2c:B8", "trade": False, "result_win": False, "break_even": 0.02},
        ]
        buckets = aggregate_calibration(rows)
        self.assertEqual(len(buckets), 2)
        b = [x for x in buckets if x.key == "1c:B9"][0]
        self.assertEqual(b.trades, 2)
        self.assertEqual(b.wins, 1)


if __name__ == "__main__":
    unittest.main()
