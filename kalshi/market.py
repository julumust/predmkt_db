import websocket
import json
import time
import threading
import requests
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

class APIClient():
    
    def __init__(self, private_key):
        self.private_key = private_key

    def get_timestamp(self):
        self.timestamp = str(int(time.time() * 1000))

    def sign_request(private_key, timestamp, method, path):
        path_without_query = path.split('?')[0]
        message = f"{timestamp}{method}{path_without_query}".encode('utf-8')
        signature = private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
                ),
                hashes.SHA256()
        )

        return base64.b64encode(signature).decode('utf-8')
    
#class WebSockerHandler():

    #def __init__(self):
        self.wsapp = websocket.WebSocketApp("wss://api.elections.kalshi.com/", on_open=self.on_open, on_message=self.on_message)
        

   # def on_open(self):
        message = {
            "KALSHI-ACCESS-KEY": your_api_key_id
            "KALSHI-ACCESS-SIGNATURE": request_signature
            "KALSHI-ACCESS-TIMESTAMP": unix_timestamp_in_milliseconds

        }
        pass

   # def on_message(self):
        pass
        


    