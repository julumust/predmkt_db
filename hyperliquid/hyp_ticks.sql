CREATE TABLE hl_outcome (
    outcome_id    BIGINT PRIMARY KEY,
    yes_coin      TEXT NOT NULL,
    no_coin       TEXT NOT NULL,
    name          TEXT,
    description   TEXT,
    underlying    TEXT,
    target_price  DOUBLE PRECISION,
    expiry        TEXT,
    period        TEXT,
    first_seen    TIMESTAMPTZ NOT NULL,
    last_seen     TIMESTAMPTZ NOT NULL
);

CREATE TABLE hl_book (
    time      TIMESTAMPTZ NOT NULL,
    coin      TEXT NOT NULL,
    side      TEXT NOT NULL,
    price     DOUBLE PRECISION NOT NULL,
    quantity  DOUBLE PRECISION NOT NULL
) WITH (tsdb.hypertable);

CREATE INDEX idx_hl_book_coin_side_time ON hl_book(coin, side, time DESC);

CREATE TABLE hl_trade (
    time      TIMESTAMPTZ NOT NULL,
    coin      TEXT NOT NULL,
    side      TEXT NOT NULL,
    price     DOUBLE PRECISION NOT NULL,
    quantity  DOUBLE PRECISION NOT NULL,
    hash      TEXT NOT NULL
) WITH (tsdb.hypertable);

CREATE INDEX idx_hl_trade_coin_time ON hl_trade(coin, time DESC);

CREATE TABLE hl_bbo (
    time      TIMESTAMPTZ NOT NULL,
    coin      TEXT NOT NULL,
    best_bid  DOUBLE PRECISION,
    best_ask  DOUBLE PRECISION,
    spread    DOUBLE PRECISION
) WITH (tsdb.hypertable);

CREATE INDEX idx_hl_bbo_coin_time ON hl_bbo(coin, time DESC);
