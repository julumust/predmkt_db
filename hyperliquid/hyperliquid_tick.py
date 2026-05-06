import websocket
import json
import time
import threading
import traceback
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timezone

BASE_URL = "wss://api.hyperliquid.xyz/ws"
INFO_URL = "https://api.hyperliquid.xyz/info"


class HLBook:
    DB_TABLE = "hl_book"
    DB_COLUMNS = ["time", "coin", "side", "price", "quantity"]
    MAX_BATCH_SIZE = 100


class HLTrade:
    DB_TABLE = "hl_trade"
    DB_COLUMNS = ["time", "coin", "side", "price", "quantity", "hash"]
    MAX_BATCH_SIZE = 50


class HLBbo:
    DB_TABLE = "hl_bbo"
    DB_COLUMNS = ["time", "coin", "best_bid", "best_ask", "spread"]
    MAX_BATCH_SIZE = 10


class HLOutcome:
    DB_TABLE = "hl_outcome"
    DB_COLUMNS = [
        "outcome_id", "yes_coin", "no_coin", "name", "description",
        "underlying", "target_price", "expiry", "period",
        "first_seen", "last_seen",
    ]


def parse_description(desc: str) -> dict:
    # HIP-4 outcomeMeta returns a pipe-delimited string, e.g.
    # "class:priceBinary|underlying:BTC|expiry:20260506-0600|targetPrice:80930|period:1d"
    out = {}
    for part in (desc or "").split("|"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k] = v
    return out


def coin_for(outcome_id: int, side: int) -> str:
    # HIP-4 WS encoding: '#<10*outcome_id + side>'. side 0 = YES, side 1 = NO.
    return f"#{10 * outcome_id + side}"


def fetch_outcomes(info_url: str = INFO_URL) -> list[dict]:
    r = requests.post(info_url, json={"type": "outcomeMeta"}, timeout=10)
    r.raise_for_status()
    body = r.json()
    enriched = []
    for o in body.get("outcomes", []) + body.get("questions", []):
        oid = int(o["outcome"])
        meta = parse_description(o.get("description", ""))
        target = meta.get("targetPrice")
        enriched.append({
            "outcome_id": oid,
            "yes_coin": coin_for(oid, 0),
            "no_coin": coin_for(oid, 1),
            "name": o.get("name"),
            "description": o.get("description"),
            "underlying": meta.get("underlying"),
            "target_price": float(target) if target is not None else None,
            "expiry": meta.get("expiry"),
            "period": meta.get("period"),
        })
    return enriched


class HyperOutcomeHandler:
    PER_MARKET_CHANNELS = ["l2Book", "trades", "bbo"]
    ROTATION_PERIOD_SECONDS = 60

    def __init__(self, conn, base_url: str = BASE_URL, info_url: str = INFO_URL):
        self.conn = conn
        self.base_url = base_url
        self.info_url = info_url
        self.ws = None
        self.current_coins: set[str] = set()
        self.book_batch: list[tuple] = []
        self.trade_batch: list[tuple] = []
        self.bbo_batch: list[tuple] = []
        self._send_lock = threading.Lock()
        self._rotation_started = False

    def _build_ws(self):
        return websocket.WebSocketApp(
            self.base_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
        )

    # Lock-guarded send so the rotation thread and the reader thread can't
    # interleave frames or race against a torn-down socket on reconnect.
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

    def _send_per_channel(self, coin: str, op: str = "subscribe"):
        for ch in self.PER_MARKET_CHANNELS:
            self._send_json({
                "method": op,
                "subscription": {"type": ch, "coin": coin},
            })

    @staticmethod
    def _coins_from(outcomes: list[dict]) -> set[str]:
        coins = set()
        for o in outcomes:
            coins.add(o["yes_coin"])
            coins.add(o["no_coin"])
        return coins

    def _upsert_outcome(self, o: dict):
        if self.conn is None:
            return
        try:
            cur = self.conn.cursor()
            now = datetime.now(timezone.utc)
            cur.execute(
                """
                INSERT INTO hl_outcome
                  (outcome_id, yes_coin, no_coin, name, description,
                   underlying, target_price, expiry, period, first_seen, last_seen)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (outcome_id) DO UPDATE
                  SET last_seen = EXCLUDED.last_seen;
                """,
                (
                    o["outcome_id"], o["yes_coin"], o["no_coin"], o["name"],
                    o["description"], o["underlying"], o["target_price"],
                    o["expiry"], o["period"], now, now,
                ),
            )
            self.conn.commit()
        except Exception as e:
            print(f"upsert outcome failed: {e}", flush=True)
            self.conn.rollback()

    def on_open(self, *_):
        try:
            outcomes = fetch_outcomes(self.info_url)
        except Exception as e:
            print(f"on_open fetch_outcomes failed: {e}", flush=True)
            outcomes = []
        for o in outcomes:
            self._upsert_outcome(o)
        self.current_coins = self._coins_from(outcomes)
        for coin in sorted(self.current_coins):
            self._send_per_channel(coin)
        if not self._rotation_started:
            self._rotation_started = True
            threading.Thread(
                target=self.schedule_rotation, daemon=True, name="hl-rotate"
            ).start()
        print(f"on_open: subscribed to {len(self.current_coins)} coins "
              f"({len(outcomes)} outcomes)", flush=True)

    # Program-lifetime thread. Polls outcomeMeta on a fixed cadence; diffs
    # against the currently-subscribed set; subscribes to new outcomes and
    # unsubscribes from ones the protocol has retired (post-settlement).
    def schedule_rotation(self):
        while True:
            time.sleep(self.ROTATION_PERIOD_SECONDS)
            try:
                outcomes = fetch_outcomes(self.info_url)
            except Exception as e:
                print(f"rotation fetch failed: {e}", flush=True)
                continue
            for o in outcomes:
                self._upsert_outcome(o)
            new_coins = self._coins_from(outcomes)
            added = new_coins - self.current_coins
            removed = self.current_coins - new_coins
            if not added and not removed:
                continue
            for coin in sorted(removed):
                self._send_per_channel(coin, op="unsubscribe")
            for coin in sorted(added):
                self._send_per_channel(coin)
            self.current_coins = new_coins
            print(f"rotated: +{len(added)} -{len(removed)}", flush=True)

    def on_message(self, _, raw):
        if raw == "Websocket connection established.":
            return
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            print(f"non-json frame: {raw}", flush=True)
            return

        channel = msg.get("channel")
        if channel in ("pong", "subscriptionResponse"):
            return

        data = msg.get("data")
        try:
            if channel == "l2Book":
                self._handle_book(data)
            elif channel == "trades":
                self._handle_trades(data)
            elif channel == "bbo":
                self._handle_bbo(data)
            else:
                print(f"unhandled channel: {channel}", flush=True)
        except Exception as e:
            print(f"dispatch error on {channel}: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()

    @staticmethod
    def _ts_from_ms(ms) -> datetime:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)

    def _handle_book(self, data):
        ts = self._ts_from_ms(data["time"])
        coin = data["coin"]
        bids, asks = data["levels"]
        rows = [(ts, coin, "bid", float(lvl["px"]), float(lvl["sz"])) for lvl in bids]
        rows += [(ts, coin, "ask", float(lvl["px"]), float(lvl["sz"])) for lvl in asks]
        self.book_batch.extend(rows)
        self._flush_if_full(self.book_batch, HLBook)

    def _handle_trades(self, data):
        for t in data:
            self.trade_batch.append((
                self._ts_from_ms(t["time"]),
                t["coin"], t["side"], float(t["px"]), float(t["sz"]), t["hash"],
            ))
        self._flush_if_full(self.trade_batch, HLTrade)

    def _handle_bbo(self, data):
        ts = self._ts_from_ms(data["time"])
        bid, ask = data["bbo"]
        bb = float(bid["px"]) if bid else None
        ba = float(ask["px"]) if ask else None
        spread = (ba - bb) if (bb is not None and ba is not None) else None
        self.bbo_batch.append((ts, data["coin"], bb, ba, spread))
        self._flush_if_full(self.bbo_batch, HLBbo)

    def _flush_if_full(self, batch, spec):
        if len(batch) >= spec.MAX_BATCH_SIZE:
            self.insert_values(batch, spec.DB_TABLE, spec.DB_COLUMNS)
            batch.clear()

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

    def on_error(self, _, error):
        print(f"error: {type(error).__name__}: {error}", flush=True)

    def on_close(self, _, code, msg):
        print(f"closed: code={code} msg={msg}", flush=True)

    def start(self):
        backoff = 1
        while True:
            self.ws = self._build_ws()
            self.ws.run_forever(ping_interval=20, ping_timeout=10)
            with self._send_lock:
                self.ws = None
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    conn = psycopg2.connect(
        database="hyperliquid",
        host="localhost",
        user="postgres",
        password="password",
        port="6543",
    )
    HyperOutcomeHandler(conn=conn).start()
