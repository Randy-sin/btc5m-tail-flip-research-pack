CREATE TABLE IF NOT EXISTS btc5m_observations (
    id INTEGER PRIMARY KEY,
    market_id TEXT NOT NULL,
    condition_id TEXT,
    token_id TEXT,
    side TEXT NOT NULL,
    ts INTEGER NOT NULL,
    window_start_ts INTEGER NOT NULL,
    window_end_ts INTEGER NOT NULL,
    seconds_remaining REAL NOT NULL,
    token_price REAL NOT NULL,
    chainlink_open_price REAL NOT NULL,
    chainlink_ref_price REAL NOT NULL,
    chainlink_close_price REAL,
    binance_mid_price REAL,
    sigma_intraround_per_s REAL,
    sigma_hourly_per_s REAL,
    hour_return REAL,
    orderbook_imbalance REAL,
    bid_depth_1 REAL,
    ask_depth_1 REAL,
    queue_ahead REAL,
    model_prob REAL,
    break_even REAL,
    b_score REAL,
    b_ratio REAL,
    edge_abs REAL,
    result_win INTEGER,
    source TEXT
);

CREATE TABLE IF NOT EXISTS clob_trades (
    id INTEGER PRIMARY KEY,
    market_id TEXT,
    condition_id TEXT,
    token_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    side TEXT,
    price REAL NOT NULL,
    size REAL NOT NULL,
    source TEXT
);

CREATE TABLE IF NOT EXISTS clob_orderbook_snapshots (
    id INTEGER PRIMARY KEY,
    market_id TEXT,
    condition_id TEXT,
    token_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    best_bid REAL,
    best_ask REAL,
    bid_levels_json TEXT,
    ask_levels_json TEXT,
    source TEXT
);
