---- Market Channel Punlic WebSocket ----

---- Book Table ----
CREATE TABLE book (
    time TIMESTAMPTZ NOT NULL,
    asset_id TEXT NOT NULL,
    market TEXT NOT NULL,
    side TEXT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    quantity DOUBLE PRECISION NOT NULL
) WITH (tsdb.hypertable);

CREATE INDEX idx_asset_side_time ON book(asset_id, side, time DESC);

---- Price Change Table ----
CREATE TABLE price_change (
    time TIMESTAMPTZ NOT NULL,
    asset_id TEXT NOT NULL,
    market TEXT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    side TEXT NOT NULL,
    best_bid DOUBLE PRECISION NOT NULL,
    best_ask DOUBLE PRECISION NOT NULL
) WITH (tsdb.hypertable);

CREATE INDEX idx_pc_asset_side_time ON price_change(asset_id, side, time DESC);

---- Last Trade Price ----
CREATE TABLE last_tp (
    time TIMESTAMPTZ NOT NULL,
    asset_id TEXT NOT NULL,
    market TEXT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    quantity DOUBLE PRECISION NOT NULL,
    side TEXT NOT NULL
) WITH (tsdb.hypertable);

CREATE INDEX idx_last_tc_asset_size_time ON last_tp(asset_id, side, time DESC);

---- Tick Size Change ----
CREATE TABLE ts_delta (
    time TIMESTAMPTZ NOT NULL,
    asset_id TEXT NOT NULL,
    market TEXT NOT NULL,
    old_ts DOUBLE PRECISION NOT NULL,
    new_ts DOUBLE PRECISION NOT NULL
) WITH (tsdb.hypertable);

CREATE INDEX idx_tsize_asset_time ON ts_delta(asset_id, time DESC);

---- Best Bid/Ask ----
CREATE TABLE best_bid_ask (
    time TIMESTAMPTZ NOT NULL,
    asset_id TEXT NOT NULL,
    market TEXT NOT NULL,
    best_bid DOUBLE PRECISION NOT NULL,
    best_ask DOUBLE PRECISION NOT NULL,
    spread DOUBLE PRECISION NOT NULL
) WITH (tsdb.hypertable);

CREATE INDEX idx_bid_ask_asset_spread_time ON best_bid_ask(asset_id, spread, time DESC);
    
---- New Market ----
CREATE TABLE new_market (
    time TIMESTAMPTZ NOT NULL,
    question TEXT NOT NULL,
    market TEXT NOT NULL,
    slug TEXT NOT NULL
) WITH (tsdb.hypertable);

CREATE INDEX idx_new_market_mkt_question_time ON new_market(market, question, time DESC);
    
---- Market Resolved ----
CREATE TABLE market_resolved (
    time TIMESTAMPTZ NOT NULL,
    id TEXT NOT NULL,
    market TEXT NOT NULL,
    asset_ids TEXT NOT NULL,
    winning_asset_id TEXT NOT NULL,
    win_outcome TEXT NOT NULL
) WITH (tsdb.hypertable);

CREATE INDEX idx_market_resolved_asset_spread_time ON market_resolved(id, asset_ids, time DESC);
