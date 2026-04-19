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

class WebSocketHandler():

    # Name of the hypertable
    DB_TABLE = "poly_ticks"
    # Columns in the hypertable in the correct order
    DB_COLUMNS = ["time","asset_id","market","side","price","quantity"]
    # Batch side used to insert data in batches
    MAX_BATCH_SIZE = 100

    def __init__(self, retrieve_ID, conn):
        self.retrieve_ID = retrieve_ID
        self.current_ids = retrieve_ID.get_assetID()
        self.conn = conn
        self.current_batch = []
        self.insert_counter = 0
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

    def insert_values(self, data):
        if self.conn is not None:
            try:
                cursor = self.conn.cursor()
                sql = f"""
                INSERT INTO {self.DB_TABLE} ({','.join(self.DB_COLUMNS)})
                VALUES %s;"""
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
                rows.append((timestamp, message["asset_id"], message["market"], "side", float(bid["price"]), float(bid["size"])))
            for ask in message["asks"]:
                rows.append((timestamp, message["asset_id"], message["market"], "side", float(ask["price"]), float(ask["size"])))
            self.current_batch.extend(rows)
            print(f"Current batch size: {len(self.current_batch)}")

            # Ingest data if max batch size is reached then reset the batch
            if len(self.current_batch) >= self.MAX_BATCH_SIZE:
                print("triggering insert...")  
                self.insert_values(self.current_batch)
                self.insert_counter += 1
                print(f"Batch insert #{self.insert_counter}")
                self.current_batch = []        

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