CREATE TABLE poly_ticks (
    time TIMESTAMPTZ NOT NULL,
    asset_id TEXT NOT NULL,
    market TEXT NOT NULL,
    side TEXT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    quantity DOUBLE PRECISION NOT NULL
) WITH (tsdb.hypertable);
---- Create Index ----
CREATE INDEX idx_asset_side_time ON poly_ticks(asset_id, side, time DESC);