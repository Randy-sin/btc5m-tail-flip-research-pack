import unittest
import numpy as np

from btc5m_tail_flip.aliplayer_full import SpotSeries, nearest_price, nearest_values, safe_div


class AliplayerFullTests(unittest.TestCase):
    def test_safe_div(self):
        self.assertEqual(safe_div(1.0, 0.0), 0.0)
        self.assertEqual(safe_div(2.0, 4.0), 0.5)

    def test_nearest_spot(self):
        s = SpotSeries(
            ts=np.array([10, 20, 30], dtype=np.int64),
            price=np.array([100.0, 101.0, 102.0]),
            sigma_i=np.array([0.1, 0.2, 0.3]),
            sigma_h=np.array([0.01, 0.02, 0.03]),
            hour_return=np.array([0.0, 0.01, 0.02]),
        )
        prices = nearest_price(s, np.array([5, 20, 25, 40], dtype=np.int64))
        self.assertEqual(prices.tolist(), [100.0, 101.0, 101.0, 102.0])
        ref, sig_i, sig_h, hour = nearest_values(s, np.array([21], dtype=np.int64))
        self.assertEqual(ref.tolist(), [101.0])
        self.assertEqual(sig_i.tolist(), [0.2])
        self.assertEqual(sig_h.tolist(), [0.02])
        self.assertEqual(hour.tolist(), [0.01])


if __name__ == "__main__":
    unittest.main()
