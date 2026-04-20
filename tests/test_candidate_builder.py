import json
import os
import tempfile
import unittest

from btc5m_tail_flip.candidate_builder import (
    gamma_meta_from_raw,
    parse_window_start,
    _levels_size_at,
)


class CandidateBuilderTests(unittest.TestCase):
    def test_parse_window_start(self):
        self.assertEqual(parse_window_start("btc-updown-5m-1773360000"), 1773360000)

    def test_levels_size_at(self):
        levels = json.dumps([{"price": 0.01, "size": 12.5}, {"price": 0.02, "size": 3.0}])
        self.assertEqual(_levels_size_at(levels, 0.01), 12.5)
        self.assertEqual(_levels_size_at(levels, 0.03), 0.0)

    def test_gamma_meta_extracts_price_and_tokens(self):
        raw = {
            "conditionId": "0xabc",
            "outcomes": "[\"Up\", \"Down\"]",
            "outcomePrices": "[\"1\", \"0\"]",
            "clobTokenIds": "[\"up-token\", \"down-token\"]",
            "events": [{"eventMetadata": {"priceToBeat": 70529.04}}],
        }
        meta = gamma_meta_from_raw("btc-updown-5m-1", raw)
        self.assertEqual(meta.price_to_beat, 70529.04)
        self.assertEqual(meta.outcome, "Up")
        self.assertEqual(meta.up_token_id, "up-token")
        self.assertEqual(meta.down_token_id, "down-token")
        self.assertEqual(meta.condition_id, "0xabc")


if __name__ == "__main__":
    unittest.main()
