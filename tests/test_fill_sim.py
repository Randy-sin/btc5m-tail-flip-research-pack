import unittest
from btc5m_tail_flip.backtest import TradeEvent, simulate_maker_buy_fill


class FillSimulationTests(unittest.TestCase):
    def test_queue_aware_full_fill(self):
        trades = [
            TradeEvent(ts=11, price=0.01, size=5, side="SELL"),
            TradeEvent(ts=12, price=0.01, size=10, side="SELL"),
            TradeEvent(ts=13, price=0.01, size=20, side="SELL"),
        ]
        res = simulate_maker_buy_fill(order_ts=10, limit_price=0.01, size=10, queue_ahead=12, trades_after=trades)
        self.assertAlmostEqual(res.filled, 10.0)
        self.assertEqual(res.remaining_self, 0.0)
        self.assertEqual(res.filled_ts, 13)

    def test_queue_aware_partial_fill(self):
        trades = [TradeEvent(ts=11, price=0.01, size=12, side="SELL")]
        res = simulate_maker_buy_fill(order_ts=10, limit_price=0.01, size=10, queue_ahead=7, trades_after=trades)
        self.assertAlmostEqual(res.filled, 5.0)
        self.assertAlmostEqual(res.fill_fraction, 0.5)

    def test_wrong_side_does_not_fill(self):
        trades = [TradeEvent(ts=11, price=0.01, size=100, side="BUY")]
        res = simulate_maker_buy_fill(order_ts=10, limit_price=0.01, size=10, queue_ahead=0, trades_after=trades)
        self.assertEqual(res.filled, 0.0)


if __name__ == "__main__":
    unittest.main()
