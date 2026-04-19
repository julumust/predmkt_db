CREATE TABLE book (
    time TIMESTAMPTZ NOT NULL,
    asset_id TEXT NOT NULL,
    market TEXT NOT NULL,
    side TEXT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    quantity DOUBLE PRECISION NOT NULL
) WITH (tsdb.hypertable);
---- Create Index ----
CREATE INDEX idx_asset_side_time ON book(asset_id, side, time DESC);

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
---- Create Index ----
CREATE INDEX idx_pc_asset_side_time ON price_change(asset_id, side, time DESC);
