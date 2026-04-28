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

class KalshiWebSocketHandler:

    ''' Connect to Kalshi Websocket and begin to ingest market data stream.'''
    def __init__(self, auth: KalshiAuth, market_tickers: list[str]):
        self.auth = auth
        self.market_tickers = market_tickers
        websocket.enableTrace(True)
        header = [f"{k}: {v}" for k, v in auth.headers().items()]
        self.ws = websocket.WebSocketApp(auth.BASE_URL,
                                         header=header,
                                         on_open=self.on_open,
                                         on_message=self.on_message,
                                         on_error=self.on_error,
                                         on_close=self.on_close)

    def on_open(self, *_args):
        subscription = {
            "id": 1,
            "cmd": "subscribe",
            "params": {
                "channels": ["orderbook_delta"],
                "market_tickers": self.market_tickers,
            },
        }
        self.ws.send(json.dumps(subscription))

    def on_message(self, *args):
        message = args[-1]
        print(message)

    def on_error(self, *args):
        print(f"error: {args[-1] if args else 'unknown'}")

    def on_close(self, *args):
        print(f"closed: {args}")

    def start(self):
        self.ws.run_forever(origin="https://kalshi.com")

if __name__ == "__main__":
    auth_client = KalshiAuth(BASE_URL=base_url, AUTH=auth, ACCESS_KEY=access_key)
    KalshiWebSocketHandler(auth_client, market_tickers=["KXNBA-26-OKC"]).start()



    





 





