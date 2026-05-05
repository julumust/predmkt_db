import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv
import os
import websocket
from datetime import datetime, timezone
import json
import threading
import traceback
import requests
import time
import psycopg2
from psycopg2.extras import execute_values

load_dotenv()

base_url = "wss://api.elections.kalshi.com/trade-api/ws/v2"
access_key = os.getenv("KALSHI_ACCESS_KEY")
auth = os.getenv("KALSHI_PRIVATE_KEY")


class KalshiAuth:
    WS_PATH = "/trade-api/ws/v2"

    def __init__(self, BASE_URL: str, AUTH: str, ACCESS_KEY: str):
        self.BASE_URL = BASE_URL
        self.ACCESS_KEY = ACCESS_KEY
        self.AUTH = AUTH
        self.private_key = self._load_private_key()

    def _load_private_key(self):
        if self.AUTH.lstrip().startswith("-----BEGIN"):
            pem_bytes = self.AUTH.encode()
        else:
            with open(self.AUTH, "rb") as f:
                pem_bytes = f.read()
        return serialization.load_pem_private_key(pem_bytes, password=None, backend=default_backend())

    def sign(self, message: str) -> str:
        signature = self.private_key.sign(
            message.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode('utf-8')

    def headers(self, method: str = "GET", path: str = WS_PATH) -> dict:
        timestamp = str(int(datetime.now(timezone.utc).timestamp() * 1000))
        signature = self.sign(timestamp + method + path.split('?')[0])
        return {
            "KALSHI-ACCESS-KEY": self.ACCESS_KEY,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
        }


class Ticker:
    def __init__(self, series_ticker: str):
        self.series_ticker = series_ticker

    def get_ticker(self):
        url = f"https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={self.series_ticker}&status=open"
        data = requests.get(url, timeout=10).json()
        ticker = None
        for item in data["markets"]:
            ticker = item.get("ticker")
        return ticker


class KalshiBook:
    DB_TABLE = "kalshi_book"
    DB_COLUMNS = ["time", "market_ticker", "outcome", "price", "quantity"]
    MAX_BATCH_SIZE = 100


class KalshiPriceChange:
    DB_TABLE = "kalshi_price_change"
    DB_COLUMNS = ["time", "market_ticker", "outcome", "price", "quantity", "best_bid", "best_ask"]
    MAX_BATCH_SIZE = 100


class KalshiLastTp:
    DB_TABLE = "kalshi_last_tp"
    DB_COLUMNS = ["time", "market_ticker", "outcome", "price", "quantity"]
    MAX_BATCH_SIZE = 10


class KalshiTsDelta:
    DB_TABLE = "kalshi_ts_delta"
    DB_COLUMNS = ["time", "market_ticker", "old_structure", "new_structure"]
    MAX_BATCH_SIZE = 10


class KalshiBestBidAsk:
    DB_TABLE = "kalshi_best_bid_ask"
    DB_COLUMNS = ["time", "market_ticker", "yes_bid", "yes_ask", "spread"]
    MAX_BATCH_SIZE = 10


class KalshiNewMarket:
    DB_TABLE = "kalshi_new_market"
    DB_COLUMNS = ["time", "market_ticker", "title", "event_ticker"]
    MAX_BATCH_SIZE = 10


class KalshiMarketResolved:
    DB_TABLE = "kalshi_market_resolved"
    DB_COLUMNS = ["time", "market_ticker", "result", "settlement_value"]
    MAX_BATCH_SIZE = 10


class LocalOrderBook:
    # Kalshi sends signed deltas, not absolute sizes. Maintain the yes/no bid
    # books locally so we can compute current quantity at a level and derive BBO.
    # Asks aren't sent natively — yes_ask = 1 - best_no_bid (and vice versa).
    def __init__(self):
        self.yes = {}
        self.no = {}

    def reset_from_snapshot(self, yes_levels, no_levels):
        self.yes = {float(p): float(s) for p, s in yes_levels}
        self.no = {float(p): float(s) for p, s in no_levels}

    def apply_delta(self, outcome, price, delta):
        book = self.yes if outcome == "yes" else self.no
        new_size = book.get(price, 0.0) + delta
        if new_size <= 0:
            book.pop(price, None)
            return 0.0
        book[price] = new_size
        return new_size

    def best_bid_ask(self, outcome):
        if outcome == "yes":
            bid = max(self.yes) if self.yes else None
            ask = (1.0 - max(self.no)) if self.no else None
        else:
            bid = max(self.no) if self.no else None
            ask = (1.0 - max(self.yes)) if self.yes else None
        return bid, ask


class KalshiWebSocketHandler:
    PER_MARKET_CHANNELS = ["orderbook_delta", "ticker", "trade"]
    ROTATION_PERIOD_SECONDS = 900

    def __init__(self, auth: KalshiAuth, market_tickers: list[str], conn, series_ticker: str):
        self.auth = auth
        self.market_tickers = market_tickers
        self.conn = conn
        self.series_ticker = series_ticker
        self.book = LocalOrderBook()
        self.book_batch = []
        self.delta_batch = []
        self.last_tp_batch = []
        self.ts_delta_batch = []
        self.bba_batch = []
        self.new_market_batch = []
        self.resolved_batch = []
        self._last_structure = {}      # market_ticker -> last seen price_level_structure
        self._sids = {}                # channel name -> sid (needed to unsubscribe on rotation)
        self._sub_id = 0
        self._send_lock = threading.Lock()
        self._rotation_started = False
        self.ws = None
        self.last_ping_ts = None
        self.last_pong_ts = None

    # Kalshi embeds signature timestamps that expire — rebuild headers per connect.
    def _build_ws(self):
        header = [f"{k}: {v}" for k, v in self.auth.headers().items()]
        return websocket.WebSocketApp(
            self.auth.BASE_URL,
            header=header,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_ping=self.on_ping,
            on_pong=self.on_pong,
        )

    def _next_id(self):
        self._sub_id += 1
        return self._sub_id

    # Serialized send across reader/rotation threads. False if socket gone.
    def _send_json(self, payload: dict) -> bool:
        with self._send_lock:
            ws = self.ws
            if ws is None:
                return False
            try:
                ws.send(json.dumps(payload))
                return True
            except Exception as e:
                print(f"send failed: {e}", flush=True)
                return False

    def on_open(self, *_):
        # Fresh connection — drop stale book and sids; snapshot will reseed.
        self.book = LocalOrderBook()
        self._sids = {}
        # One subscribe per channel so each `subscribed` ack maps cleanly to one sid.
        for ch in self.PER_MARKET_CHANNELS:
            self._send_json({
                "id": self._next_id(),
                "cmd": "subscribe",
                "params": {"channels": [ch], "market_tickers": self.market_tickers},
            })
        # market_lifecycle_v2 takes no filter params (global). We filter in-handler.
        self._send_json({
            "id": self._next_id(),
            "cmd": "subscribe",
            "params": {"channels": ["market_lifecycle_v2"]},
        })

    def on_message(self, _, raw):
        msg = json.loads(raw)
        msg_type = msg.get("type")
        if msg_type == "subscribed":
            body = msg.get("msg") or {}
            channel = body.get("channel")
            sid = msg.get("sid") if msg.get("sid") is not None else body.get("sid")
            if channel and sid is not None:
                self._sids[channel] = sid
            return
        if msg_type in (None, "unsubscribed", "ok"):
            return
        if msg_type == "error":
            print(f"server error: {msg}", flush=True)
            return
        body = msg.get("msg") or {}
        try:
            if msg_type == "orderbook_snapshot":
                self._handle_snapshot(body)
            elif msg_type == "orderbook_delta":
                self._handle_delta(body)
            elif msg_type == "ticker":
                self._handle_ticker(body)
            elif msg_type == "trade":
                self._handle_trade(body)
            elif msg_type == "market_lifecycle_v2":
                self._handle_lifecycle(body)
        except Exception as e:
            print(f"dispatch error on {msg_type}: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()

    @staticmethod
    def _ts_from_ms(ms):
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)

    @staticmethod
    def _ts_now():
        return datetime.now(timezone.utc)

    def _flush_if_full(self, batch, spec):
        if len(batch) >= spec.MAX_BATCH_SIZE:
            self.insert_values(batch, spec.DB_TABLE, spec.DB_COLUMNS)
            batch.clear()

    def _upsert_market(self, market_ticker, market_id):
        if self.conn is None or not market_ticker:
            return
        try:
            cur = self.conn.cursor()
            now = self._ts_now()
            cur.execute(
                """
                INSERT INTO kalshi_markets (market_ticker, market_id, series_ticker, first_seen_ts, last_seen_ts)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (market_ticker) DO UPDATE
                  SET market_id    = COALESCE(kalshi_markets.market_id, EXCLUDED.market_id),
                      last_seen_ts = EXCLUDED.last_seen_ts;
                """,
                (market_ticker, market_id, self.series_ticker, now, now),
            )
            self.conn.commit()
        except Exception as e:
            print(f"market upsert failed: {e}", flush=True)
            self.conn.rollback()

    def _handle_snapshot(self, msg):
        yes_levels = msg.get("yes_dollars_fp", [])
        no_levels = msg.get("no_dollars_fp", [])
        self.book.reset_from_snapshot(yes_levels, no_levels)
        ts = self._ts_now()  # snapshot frame has no ts_ms per docs
        ticker = msg.get("market_ticker")
        self._upsert_market(ticker, msg.get("market_id"))
        for p, s in yes_levels:
            self.book_batch.append((ts, ticker, "yes", float(p), float(s)))
        for p, s in no_levels:
            self.book_batch.append((ts, ticker, "no", float(p), float(s)))
        self._flush_if_full(self.book_batch, KalshiBook)

    def _handle_delta(self, msg):
        # ts_ms is optional on orderbook_delta per Kalshi docs.
        ts_ms = msg.get("ts_ms")
        ts = self._ts_from_ms(ts_ms) if ts_ms is not None else self._ts_now()
        outcome = msg["side"]
        price = float(msg["price_dollars"])
        delta = float(msg["delta_fp"])
        new_size = self.book.apply_delta(outcome, price, delta)
        bb, ba = self.book.best_bid_ask(outcome)
        self.delta_batch.append((
            ts, msg["market_ticker"], outcome, price, new_size, bb, ba
        ))
        self._flush_if_full(self.delta_batch, KalshiPriceChange)

    def _handle_ticker(self, msg):
        ts = self._ts_from_ms(msg["ts_ms"])
        yes_bid = float(msg["yes_bid_dollars"]) if msg.get("yes_bid_dollars") is not None else None
        yes_ask = float(msg["yes_ask_dollars"]) if msg.get("yes_ask_dollars") is not None else None
        spread = (yes_ask - yes_bid) if (yes_bid is not None and yes_ask is not None) else None
        self.bba_batch.append((ts, msg["market_ticker"], yes_bid, yes_ask, spread))
        self._flush_if_full(self.bba_batch, KalshiBestBidAsk)

    def _handle_trade(self, msg):
        ts = self._ts_from_ms(msg["ts_ms"])
        taker_side = msg["taker_side"]
        price_field = "yes_price_dollars" if taker_side == "yes" else "no_price_dollars"
        price = float(msg[price_field])
        qty = float(msg["count_fp"])
        self.last_tp_batch.append((ts, msg["market_ticker"], taker_side, price, qty))
        self._flush_if_full(self.last_tp_batch, KalshiLastTp)

    def _handle_lifecycle(self, msg):
        event_type = msg.get("event_type")
        ticker = msg.get("market_ticker") or ""
        meta = msg.get("additional_metadata") or {}
        # Lifecycle channel is global — filter to our series. additional_metadata
        # is only populated on `created` events per docs, so filter on
        # market_ticker (always present) instead of meta.event_ticker.
        if self.series_ticker and not ticker.startswith(self.series_ticker):
            return
        event_ticker = meta.get("event_ticker") or ""
        if event_type == "created":
            self.new_market_batch.append((
                self._ts_now(), ticker, meta.get("title"), event_ticker
            ))
            self._flush_if_full(self.new_market_batch, KalshiNewMarket)
        elif event_type == "determined":
            ts_ms = msg.get("determination_ts")
            ts = self._ts_from_ms(ts_ms) if ts_ms else self._ts_now()
            settlement = msg.get("settlement_value")
            settlement_f = float(settlement) if settlement is not None else None
            self.resolved_batch.append((
                ts, ticker, msg.get("result"), settlement_f
            ))
            self._flush_if_full(self.resolved_batch, KalshiMarketResolved)
        elif event_type == "price_level_structure_updated":
            new_structure = msg.get("price_level_structure")
            old_structure = self._last_structure.get(ticker)
            self.ts_delta_batch.append((
                self._ts_now(), ticker, old_structure, new_structure
            ))
            self._last_structure[ticker] = new_structure
            self._flush_if_full(self.ts_delta_batch, KalshiTsDelta)

    def insert_values(self, data, table, columns):
        if self.conn is None or not data:
            return
        try:
            cur = self.conn.cursor()
            sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES %s;"
            execute_values(cur, sql, data)
            self.conn.commit()
            print(f"inserted {len(data)} → {table}", flush=True)
        except Exception as e:
            print(f"insert error on {table}: {e}", flush=True)
            self.conn.rollback()

    def schedule_rotation(self):
        # Program-lifetime thread. Sleeps until the next 15-min boundary, fetches
        # the new open ticker, and unsub/subs the per-market channels. The
        # lifecycle channel is global and stays subscribed across rotations.
        while True:
            try:
                next_boundary = (int(time.time() // self.ROTATION_PERIOD_SECONDS) + 1) * self.ROTATION_PERIOD_SECONDS
                time.sleep(max(0.0, next_boundary - time.time()))
                # Fetch *after* the boundary so REST returns the freshly-opened market.
                try:
                    new_ticker = Ticker(series_ticker=self.series_ticker).get_ticker()
                except Exception as e:
                    print(f"rotation: get_ticker failed: {e}", flush=True)
                    continue
                if not new_ticker or [new_ticker] == self.market_tickers:
                    continue

                ok = True
                # Unsubscribe per-market channels by their captured sids.
                for ch in self.PER_MARKET_CHANNELS:
                    sid = self._sids.get(ch)
                    if sid is None:
                        continue
                    if not self._send_json({"id": self._next_id(), "cmd": "unsubscribe", "params": {"sids": [sid]}}):
                        ok = False
                        break
                    self._sids.pop(ch, None)

                # Subscribe new market on each per-market channel.
                if ok:
                    self.market_tickers = [new_ticker]
                    self.book = LocalOrderBook()  # snapshot for new market will reseed
                    for ch in self.PER_MARKET_CHANNELS:
                        if not self._send_json({
                            "id": self._next_id(),
                            "cmd": "subscribe",
                            "params": {"channels": [ch], "market_tickers": self.market_tickers},
                        }):
                            ok = False
                            break

                if ok:
                    print(f"rotated → {new_ticker}", flush=True)
                else:
                    print("rotation deferred to reconnect (send failed)", flush=True)
            except Exception as e:
                print(f"rotation loop error: {type(e).__name__}: {e}", flush=True)
                traceback.print_exc()
                time.sleep(1)

    def on_error(self, _, error):
        print(f"error: {type(error).__name__}: {error}", flush=True)

    def on_close(self, _, code, msg):
        print(f"closed: code={code} msg={msg}", flush=True)

    def on_ping(self, *_):
        self.last_ping_ts = time.time()

    def on_pong(self, *_):
        self.last_pong_ts = time.time()

    def start(self):
        # Rotation runs for the lifetime of the process, not per-connection.
        if not self._rotation_started:
            self._rotation_started = True
            threading.Thread(target=self.schedule_rotation, daemon=True, name="kalshi-rotate").start()

        backoff = 1
        # Rolling our own reconnect so each attempt rebuilds signed headers.
        while True:
            # Refresh ticker before reconnecting in case rotation happened during the dead window.
            try:
                refreshed = Ticker(series_ticker=self.series_ticker).get_ticker()
                if refreshed:
                    self.market_tickers = [refreshed]
            except Exception as e:
                print(f"ticker refresh failed: {e}", flush=True)

            self.ws = self._build_ws()
            self.ws.run_forever(
                origin="https://kalshi.com",
                ping_interval=20,
                ping_timeout=10,
            )
            with self._send_lock:
                self.ws = None
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    conn = psycopg2.connect(
        database="kalshi",
        host="localhost",
        user="postgres",
        password="password",
        port="6543",
    )
    auth_client = KalshiAuth(BASE_URL=base_url, AUTH=auth, ACCESS_KEY=access_key)
    series_ticker = "KXBTC15M"
    market_ticker = Ticker(series_ticker=series_ticker).get_ticker()
    KalshiWebSocketHandler(
        auth=auth_client,
        market_tickers=[market_ticker],
        conn=conn,
        series_ticker=series_ticker,
    ).start()
