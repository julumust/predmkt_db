import websocket
import json
import time
import threading
import requests
import psycopg2
from datetime import datetime, timezone
from psycopg2.extras import execute_values

class GetCryptoID():

    def __init__(self, tickers):
        self.tickers = tickers
        self.token = []

    def get_assetID(self): # Retrieves current clobTokenID by retrieving current market slug
        now = int(time.time())
        current_boundary = (now // 300) * 300
        self.token = []
        for i in self.tickers:
            slug = f"{i}-updown-5m-{current_boundary}"
            r = requests.get("https://gamma-api.polymarket.com/markets", params={"slug": slug})
            raw_ids = r.json()[0]["clobTokenIds"]
            parsed_ids = json.loads(raw_ids)
            self.token.extend(parsed_ids)
        return self.token

    def get_updatedID(self): # Retrieves future market clobTokenID by retrieving next current market slug
        now = int(time.time())
        next_boundary = (now // 300 + 1) * 300
        self.token = []
        for i in self.tickers:
            slug = f"{i}-updown-5m-{next_boundary}"
            r = requests.get("https://gamma-api.polymarket.com/markets", params={"slug": slug})
            raw_ids = r.json()[0]["clobTokenIds"]
            parsed_ids = json.loads(raw_ids)
            self.token.extend(parsed_ids)
        return self.token

class OrderBook():
    DB_TABLE = "book" # Name of the hypertable
    DB_COLUMNS = ["time","asset_id","market","side","price","quantity"] # Columns in the hypertable in the correct order
    MAX_BATCH_SIZE = 100 # Batch side used to insert data in batches

class PriceChange():
    DB_TABLE = "price_change"
    DB_COLUMNS = ["time","asset_id","market","price","quantity","side", "best_bid", "best_ask"]
    MAX_BATCH_SIZE = 1000

class LastTradePrice():
    DB_TABLE = "last_tp"
    DB_COLUMNS = ["time","asset_id","market","price","quantity","side"]
    MAX_BATCH_SIZE = 100

class TickSizeChange():
    DB_TABLE = "ts_delta"
    DB_COLUMNS = ["time","asset_id","market","old_ts", "new_ts"]
    MAX_BATCH_SIZE = 100   

class BestBidAsk():
    DB_TABLE = "best_bid_ask"
    DB_COLUMNS = ["time","asset_id","market","best_bid","best_ask","spread"]
    MAX_BATCH_SIZE = 100

class NewMarket():
    DB_TABLE = "new_market"
    DB_COLUMNS = ["time","question","market","slug"]
    MAX_BATCH_SIZE = 10

class MarketResolved():
    DB_TABLE = "market_resolved"
    DB_COLUMNS = ["time","id","market","asset_ids","winning_asset_id","win_outcome"]
    MAX_BATCH_SIZE = 10 

class WebSocketHandler():
    
    def __init__(self, retrieve_ID, conn):
        self.retrieve_ID = retrieve_ID
        self.current_ids = retrieve_ID.get_assetID()
        self.conn = conn
        self.book_batch = []
        self.delta_batch = []
        self.last_trade_price = []
        self.tick_delta = []
        self.bidask = []
        self.new_market = []
        self.market_resolved = []
        self.wsapp = websocket.WebSocketApp("wss://ws-subscriptions-clob.polymarket.com/ws/market", on_open=self.on_open, on_message=self.on_message)

    def schedule_rotation(self): # Updates initial subscription message to new market clobTokenID
        while True:
            now = time.time()
            next_boundary = (int(now // 300) + 1) * 300
            new_ids = self.retrieve_ID.get_updatedID()
            time.sleep(next_boundary - now)
            try:
                if new_ids and new_ids != self.current_ids:
                    self.wsapp.send(json.dumps({"operation": "unsubscribe", "assets_ids": self.current_ids}))
                    self.wsapp.send(json.dumps({"operation": "subscribe", "assets_ids": new_ids}))
                    print("Rotated successfully")
                    self.current_ids = new_ids
            except Exception as e:
                print("Rotation error:", e)

    def insert_values(self, data, table, columns):
        if self.conn is not None:
            try:
                cursor = self.conn.cursor()
                sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES %s;"
                execute_values(cursor, sql, data)
                self.conn.commit()
                print("Insert successful")
            except Exception as e:
                print("Insert error", e)
                self.conn.rollback()

    def on_open(self, wsapp): # Initial request
        message = {
            "assets_ids": self.current_ids,
            "type": "market",
            "custom_feature_enabled": True,
        }
        wsapp.send(json.dumps(message))
        threading.Thread(target=self.schedule_rotation, daemon=True).start()

        def ping():
            while True:
                wsapp.send(json.dumps({}))
                time.sleep(10)

        threading.Thread(target=ping, daemon=True).start()

    def on_message(self, wsapp, message):
        message = json.loads(message)
        if message["event_type"] == "book":
            timestamp = datetime.fromtimestamp(int(message["timestamp"]) / 1000, tz = timezone.utc)
            rows = []
            for bid in message["bids"]:
                rows.append((timestamp, message["asset_id"], message["market"], "bid", float(bid["price"]), float(bid["size"])))
            for ask in message["asks"]:
                rows.append((timestamp, message["asset_id"], message["market"], "ask", float(ask["price"]), float(ask["size"])))
            self.book_batch.extend(rows)


            if len(self.book_batch) >= OrderBook.MAX_BATCH_SIZE:
                self.insert_values(self.book_batch, OrderBook.DB_TABLE, OrderBook.DB_COLUMNS)
                self.book_batch = []

        elif message["event_type"] == "price_change":
            timestamp = datetime.fromtimestamp(int(message["timestamp"]) / 1000, tz=timezone.utc)
            rows = []

            for change in message["price_changes"]:
                rows.append((timestamp, change["asset_id"], message["market"], float(change["price"]), float(change["size"]), change["side"], float(change["best_bid"]), float(change["best_ask"])))
            self.delta_batch.extend(rows)

            if len(self.delta_batch) >= PriceChange.MAX_BATCH_SIZE:
                self.insert_values(self.delta_batch, PriceChange.DB_TABLE, PriceChange.DB_COLUMNS)
                self.delta_batch = []

        elif message["event_type"] == "last_trade_price":
            timestamp = datetime.fromtimestamp(int(message["timestamp"]) / 1000, tz=timezone.utc)
            self.last_trade_price.append((
                timestamp,
                message["asset_id"],
                message["market"],
                float(message["price"]),
                float(message["size"]),
                message["side"]
                ))
                
            if len(self.last_trade_price) >= LastTradePrice.MAX_BATCH_SIZE:
                self.insert_values(self.last_trade_price, LastTradePrice.DB_TABLE, LastTradePrice.DB_COLUMNS)
                self.last_trade_price = []

        elif message["event_type"] == "tick_size_change":
            timestamp = datetime.fromtimestamp(int(message["timestamp"]) / 1000, tz=timezone.utc)
            self.tick_delta.append((
                timestamp,
                message["asset_id"],
                message["market"],
                float(message["old_tick_size"]),
                float(message["new_tick_size"])
                ))
                
            if len(self.tick_delta) >= TickSizeChange.MAX_BATCH_SIZE:
                self.insert_values(self.tick_delta, TickSizeChange.DB_TABLE, TickSizeChange.DB_COLUMNS)
                self.tick_delta = []

        elif message["event_type"] == "best_bid_ask":
            timestamp = datetime.fromtimestamp(int(message["timestamp"]) / 1000, tz=timezone.utc)
            self.bidask.append((
                timestamp,
                message["asset_id"],
                message["market"],
                float(message["best_bid"]),
                float(message["best_ask"]),
                float(message["spread"])
                ))
            
            if len(self.bidask) >= BestBidAsk.MAX_BATCH_SIZE:
                self.insert_values(self.bidask, BestBidAsk.DB_TABLE, BestBidAsk.DB_COLUMNS)
                self.bidask = []

        elif message["event_type"] == "new_market":
            timestamp = datetime.fromtimestamp(int(message["timestamp"]) / 1000, tz=timezone.utc)
            self.new_market.append((
                timestamp,
                message["question"],
                message["market"],
                message["slug"]
                ))
                
            if len(self.new_market) >= NewMarket.MAX_BATCH_SIZE:
                self.insert_values(self.new_market, NewMarket.DB_TABLE, NewMarket.DB_COLUMNS)
                self.new_market = []

        elif message["event_type"] == "market_resolved":
            timestamp = datetime.fromtimestamp(int(message["timestamp"]) / 1000, tz=timezone.utc)
            self.market_resolved.append((
                timestamp,
            message["id"],
            message["market"],
            message["assets_ids"],      # this is a list — store as array/json in your DB
            message["winning_asset_id"],
            message["winning_outcome"]
            ))

            if len(self.market_resolved) >= MarketResolved.MAX_BATCH_SIZE:
                self.insert_values(self.market_resolved, MarketResolved.DB_TABLE, MarketResolved.DB_COLUMNS)
                self.market_resolved = []
    
    def start(self):
        self.wsapp.run_forever()

if __name__ == "__main__":
    conn = psycopg2.connect(database="polymarket",
                            host="localhost",
                            user="postgres",
                            password="password",
                            port="6543"
                            )
    retrieve_ID = GetCryptoID(["btc"])
    handler = WebSocketHandler(retrieve_ID, conn)
    handler.start()