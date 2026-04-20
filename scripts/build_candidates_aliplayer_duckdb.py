#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main() -> int:
    p = argparse.ArgumentParser(description="Fast DuckDB full scan for aliplayer1 BTC 5m candidates.")
    p.add_argument("--data-dir", default="data/hf_aliplayer_btc_core")
    p.add_argument("--out", default="data/real_candidates_aliplayer_btc5m_full.csv")
    p.add_argument("--summary", default="reports/build_candidates_aliplayer_duckdb_summary.json")
    p.add_argument("--threads", type=int, default=8)
    args = p.parse_args()

    try:
        import duckdb
    except Exception as e:
        raise SystemExit("duckdb is required. Use .venv_duckdb/bin/python or install duckdb.") from e

    data_dir = args.data_dir if os.path.isabs(args.data_dir) else os.path.join(ROOT, args.data_dir)
    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    summary_path = args.summary if os.path.isabs(args.summary) else os.path.join(ROOT, args.summary)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)

    markets = os.path.join(data_dir, "data__markets.parquet")
    orderbook = os.path.join(data_dir, "data__orderbook__crypto=BTC__timeframe=5-minute__part-0.parquet")
    spot = os.path.join(data_dir, "data__spot_prices__part-0.parquet")

    con = duckdb.connect()
    con.sql(f"PRAGMA threads={int(args.threads)}")
    con.sql("PRAGMA preserve_insertion_order=false")
    started = time.time()
    query = f"""
COPY (
WITH markets AS (
  SELECT CAST(market_id AS VARCHAR) market_id, condition_id, up_token_id, down_token_id,
         CAST(end_ts AS BIGINT) window_end_ts, CAST(end_ts - 300 AS BIGINT) window_start_ts
  FROM read_parquet('{markets}')
  WHERE crypto='BTC' AND timeframe='5-minute'
), spot0 AS (
  SELECT CAST(floor(ts_ms/1000) AS BIGINT) ts, CAST(price AS DOUBLE) price
  FROM read_parquet('{spot}')
  WHERE symbol='btc/usd'
), spot1 AS (
  SELECT ts, any_value(price) price FROM spot0 GROUP BY ts
), spot2 AS (
  SELECT ts, price, ln(price) - lag(ln(price)) OVER (ORDER BY ts) AS log_ret, ln(price) AS log_price
  FROM spot1
), spot AS (
  SELECT ts, price,
         COALESCE(stddev_samp(log_ret) OVER (ORDER BY ts ROWS BETWEEN 300 PRECEDING AND CURRENT ROW), 0.00008) sigma_i,
         COALESCE(stddev_samp(log_ret) OVER (ORDER BY ts ROWS BETWEEN 3600 PRECEDING AND CURRENT ROW), 0.00006) sigma_h,
         COALESCE(log_price - lag(log_price, 3600) OVER (ORDER BY ts), 0.0) hour_return
  FROM spot2
), ob_bounds AS (
  SELECT CAST(floor(min(ts_ms)/1000) AS BIGINT) min_ts
  FROM read_parquet('{orderbook}')
), price_long AS (
  SELECT CAST(p.market_id AS VARCHAR) market_id, CAST(p.timestamp AS BIGINT) ts,
         m.window_start_ts, m.window_end_ts, 'UP' AS side,
         CAST(p.up_price AS DOUBLE) token_price, m.up_token_id AS token_id, m.condition_id
  FROM read_parquet('{os.path.join(data_dir, "data__prices__crypto=BTC__timeframe=5-minute__part-0.parquet")}') p
  JOIN markets m ON CAST(p.market_id AS VARCHAR)=m.market_id
  CROSS JOIN ob_bounds b
  WHERE p.timestamp >= b.min_ts
    AND p.up_price BETWEEN 0.009999 AND 0.020001
    AND (m.window_end_ts - CAST(p.timestamp AS BIGINT)) BETWEEN 8 AND 120
  UNION ALL
  SELECT CAST(p.market_id AS VARCHAR) market_id, CAST(p.timestamp AS BIGINT) ts,
         m.window_start_ts, m.window_end_ts, 'DOWN' AS side,
         CAST(p.down_price AS DOUBLE) token_price, m.down_token_id AS token_id, m.condition_id
  FROM read_parquet('{os.path.join(data_dir, "data__prices__crypto=BTC__timeframe=5-minute__part-0.parquet")}') p
  JOIN markets m ON CAST(p.market_id AS VARCHAR)=m.market_id
  CROSS JOIN ob_bounds b
  WHERE p.timestamp >= b.min_ts
    AND p.down_price BETWEEN 0.009999 AND 0.020001
    AND (m.window_end_ts - CAST(p.timestamp AS BIGINT)) BETWEEN 8 AND 120
), cand AS (
  SELECT *,
         row_number() OVER (
           PARTITION BY market_id, side, ts, CAST(round(token_price*100) AS INTEGER)
           ORDER BY ts
         ) rn
  FROM price_long
), ob AS (
  SELECT CAST(market_id AS VARCHAR) market_id, token_id,
         CAST(floor(ts_ms/1000) AS BIGINT) ts,
         CAST(best_bid AS DOUBLE) best_bid,
         CAST(best_ask AS DOUBLE) best_ask,
         CAST(best_bid_size AS DOUBLE) best_bid_size,
         CAST(best_ask_size AS DOUBLE) best_ask_size
  FROM read_parquet('{orderbook}')
), joined AS (
  SELECT c.*, ob.best_bid, ob.best_ask, ob.best_bid_size, ob.best_ask_size
  FROM (SELECT * FROM cand WHERE rn=1) c
  ASOF LEFT JOIN ob
    ON c.market_id=ob.market_id AND c.token_id=ob.token_id AND c.ts >= ob.ts
)
SELECT c.market_id, c.ts, c.window_start_ts, c.window_end_ts, c.side, c.token_price,
       op.price AS chainlink_open_price,
       ref.price AS chainlink_ref_price,
       cl.price AS chainlink_close_price,
       NULL::DOUBLE AS binance_mid_price,
       ref.sigma_i AS sigma_intraround_per_s,
       ref.sigma_h AS sigma_hourly_per_s,
       ref.hour_return AS hour_return,
       COALESCE((c.best_bid_size-c.best_ask_size)/NULLIF(c.best_bid_size+c.best_ask_size,0), 0.0) AS orderbook_imbalance,
       COALESCE(c.best_bid_size, 0.0) AS bid_depth_1,
       COALESCE(c.best_ask_size, 0.0) AS ask_depth_1,
       'hf_aliplayer_full_duckdb' AS source,
       c.condition_id, c.token_id,
       CASE WHEN cl.price >= op.price THEN 'UP' ELSE 'DOWN' END AS settled_side,
       CASE WHEN abs(COALESCE(c.best_bid, -1.0) - c.token_price) < 0.005001 THEN COALESCE(c.best_bid_size, 0.0) ELSE 0.0 END AS queue_ahead,
       c.best_ask
FROM joined c
ASOF LEFT JOIN spot ref ON c.ts >= ref.ts
ASOF LEFT JOIN spot op ON c.window_start_ts >= op.ts
ASOF LEFT JOIN spot cl ON c.window_end_ts >= cl.ts
) TO '{out}' (HEADER, DELIMITER ',');
"""
    con.sql(query)
    elapsed = time.time() - started
    row_count = con.sql(f"SELECT count(*) FROM read_csv_auto('{out}')").fetchone()[0]
    summary = {
        "out": out,
        "rows": int(row_count),
        "elapsed_s": elapsed,
        "threads": args.threads,
        "data_dir": data_dir,
        "source": "aliplayer1/polymarket-crypto-updown BTC 5m orderbook + spot_prices",
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
