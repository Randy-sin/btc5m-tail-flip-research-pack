import importlib.util
import sys
import unittest
from pathlib import Path


def _load_live_loop_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "live_probe_v7" / "scripts" / "v1_live_probe_loop.py"
    spec = importlib.util.spec_from_file_location("v1_live_probe_loop_for_tests", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ChainlinkOpenGuardTests(unittest.TestCase):
    def test_accepts_open_tick_within_lag(self):
        module = _load_live_loop_module()
        state = module.ChainlinkState()
        state.ticks = [(1000.0, 75000.0), (1001.0, 75001.0)]

        price, tick_ts, status = state.open_for_window(1000, max_open_tick_lag_s=5.0)

        self.assertEqual(price, 75000.0)
        self.assertEqual(tick_ts, 1000.0)
        self.assertEqual(status, "ok")

    def test_rejects_mid_window_first_tick_as_open(self):
        module = _load_live_loop_module()
        state = module.ChainlinkState()
        state.ticks = [(1120.0, 75120.0)]

        price, tick_ts, status = state.open_for_window(1000, max_open_tick_lag_s=5.0)

        self.assertIsNone(price)
        self.assertEqual(tick_ts, 1120.0)
        self.assertEqual(status, "open_tick_late")

        price2, tick_ts2, status2 = state.open_for_window(1000, max_open_tick_lag_s=5.0)
        self.assertIsNone(price2)
        self.assertIsNone(tick_ts2)
        self.assertEqual(status2, "open_tick_late")


if __name__ == "__main__":
    unittest.main()
