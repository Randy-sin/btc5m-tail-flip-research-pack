import unittest

from btc5m_tail_flip.hf_ingest import hf_resolve_url, safe_local_name, brock_remote_paths_for_date


class HfIngestTests(unittest.TestCase):
    def test_resolve_url(self):
        url = hf_resolve_url("owner/repo", "dir/file.parquet")
        self.assertEqual(url, "https://huggingface.co/datasets/owner/repo/resolve/main/dir/file.parquet")

    def test_safe_local_name(self):
        self.assertEqual(safe_local_name("orderbooks/2026-03-13.parquet"), "orderbooks__2026-03-13.parquet")

    def test_brock_paths_include_core_tables(self):
        paths = brock_remote_paths_for_date("2026-03-13")
        self.assertIn("markets/all.parquet", paths)
        self.assertIn("resolutions/all.parquet", paths)
        self.assertIn("orderbooks/2026-03-13.parquet", paths)
        self.assertIn("trades/2026-03-13.parquet", paths)


if __name__ == "__main__":
    unittest.main()
