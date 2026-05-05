---- Kalshi Public WebSocket ----
--
-- `outcome` = 'yes' | 'no' (binary leg). Distinct from Polymarket's `side`
-- (bid/ask) on purpose to avoid cross-venue join confusion.
-- Kalshi sends only the BID side of each leg natively. Asks are derived
-- (yes_ask = 1 - best_no_bid). kalshi_book / kalshi_price_change rows are
-- therefore implicit bid-book entries.

---- Markets Catalog (not a hypertable — point-lookup by ticker) ----
CREATE TABLE kalshi_markets (
    market_ticker  TEXT PRIMARY KEY,
    market_id      UUID,
    series_ticker  TEXT,
    first_seen_ts  TIMESTAMPTZ NOT NULL,
    last_seen_ts   TIMESTAMPTZ NOT NULL
);

---- Book Table ----
CREATE TABLE kalshi_book (
    time           TIMESTAMPTZ      NOT NULL,
    market_ticker  TEXT             NOT NULL,
    outcome        TEXT             NOT NULL,
    price          DOUBLE PRECISION NOT NULL,
    quantity       DOUBLE PRECISION NOT NULL
) WITH (tsdb.hypertable);

CREATE INDEX idx_kalshi_book_ticker_outcome_time ON kalshi_book(market_ticker, outcome, time DESC);

---- Price Change Table ----
CREATE TABLE kalshi_price_change (
    time           TIMESTAMPTZ      NOT NULL,
    market_ticker  TEXT             NOT NULL,
    outcome        TEXT             NOT NULL,
    price          DOUBLE PRECISION NOT NULL,
    quantity       DOUBLE PRECISION NOT NULL,
    best_bid       DOUBLE PRECISION,
    best_ask       DOUBLE PRECISION
) WITH (tsdb.hypertable);

CREATE INDEX idx_kalshi_pc_ticker_outcome_time ON kalshi_price_change(market_ticker, outcome, time DESC);

---- Last Trade Price ----
CREATE TABLE kalshi_last_tp (
    time           TIMESTAMPTZ      NOT NULL,
    market_ticker  TEXT             NOT NULL,
    outcome        TEXT             NOT NULL,
    price          DOUBLE PRECISION NOT NULL,
    quantity       DOUBLE PRECISION NOT NULL
) WITH (tsdb.hypertable);

CREATE INDEX idx_kalshi_last_tp_ticker_outcome_time ON kalshi_last_tp(market_ticker, outcome, time DESC);

---- Tick Size / Price Level Structure Change ----
CREATE TABLE kalshi_ts_delta (
    time           TIMESTAMPTZ NOT NULL,
    market_ticker  TEXT        NOT NULL,
    old_structure  TEXT,
    new_structure  TEXT
) WITH (tsdb.hypertable);

CREATE INDEX idx_kalshi_ts_delta_ticker_time ON kalshi_ts_delta(market_ticker, time DESC);

---- Best Bid/Ask ----
CREATE TABLE kalshi_best_bid_ask (
    time           TIMESTAMPTZ      NOT NULL,
    market_ticker  TEXT             NOT NULL,
    yes_bid        DOUBLE PRECISION,
    yes_ask        DOUBLE PRECISION,
    spread         DOUBLE PRECISION
) WITH (tsdb.hypertable);

CREATE INDEX idx_kalshi_bba_ticker_spread_time ON kalshi_best_bid_ask(market_ticker, spread, time DESC);

---- New Market ----
CREATE TABLE kalshi_new_market (
    time           TIMESTAMPTZ NOT NULL,
    market_ticker  TEXT        NOT NULL,
    title          TEXT,
    event_ticker   TEXT
) WITH (tsdb.hypertable);

CREATE INDEX idx_kalshi_new_market_ticker_event_time ON kalshi_new_market(market_ticker, event_ticker, time DESC);

---- Market Resolved ----
CREATE TABLE kalshi_market_resolved (
    time              TIMESTAMPTZ      NOT NULL,
    market_ticker     TEXT             NOT NULL,
    result            TEXT,
    settlement_value  DOUBLE PRECISION
) WITH (tsdb.hypertable);

CREATE INDEX idx_kalshi_market_resolved_ticker_result_time ON kalshi_market_resolved(market_ticker, result, time DESC);
