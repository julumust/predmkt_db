import websocket
import json
import time
import threading
import requests

def get_assetID(): # Retrieves current clobTokenID by retrieving current market slug
    now = int(time.time())
    current_boundary = (now // 300) * 300
    ticker = ["btc", "eth", "sol", "xrp"]
    token = []
    for i in ticker:
        slug = f"{i}-updown-5m-{current_boundary}"
        r = requests.get("https://gamma-api.polymarket.com/markets", params={"slug": slug})
        raw_ids = r.json()[0]["clobTokenIds"]
        parsed_ids = json.loads(raw_ids)
        token.extend(parsed_ids)
    return token

def get_updatedID(): # Retrieves future market clobTokenID by retrieving next current market slug
    now = int(time.time())
    next_boundary = (now // 300 + 1) * 300
    ticker = ["btc", "eth", "sol", "xrp"]
    token = []
    for i in ticker:
        slug = f"{i}-updown-5m-{next_boundary}"
        r = requests.get("https://gamma-api.polymarket.com/markets", params={"slug": slug})
        raw_ids = r.json()[0]["clobTokenIds"]
        parsed_ids = json.loads(raw_ids)
        token.extend(parsed_ids)
    return token

current_ids = get_assetID()

def schedule_rotation(wsapp): # Updates initial subscription message to new market clobTokenID
    global current_ids
    while True:
        now = time.time()
        next_boundary = (int(now // 300) + 1) * 300
        new_ids = get_updatedID()
        time.sleep(next_boundary - now)
        try:
            if new_ids and new_ids != current_ids:
                wsapp.send(json.dumps({"operation": "unsubscribe", "assets_ids": current_ids}))
                wsapp.send(json.dumps({"operation": "subscribe", "assets_ids": new_ids}))
                print("Rotated successully")
                current_ids = new_ids
        except Exception as e:
            print("Rotation error:", e)

def on_open(wsapp): # Initial requesta
    message = {
        "assets_ids": current_ids, 
        "type": "market",
        "custom_feature_enabled": True,
    }

    wsapp.send(json.dumps(message))
    threading.Thread(target=schedule_rotation, args=(wsapp,), daemon=True).start()

    def ping():
        while True:
            wsapp.send(json.dumps({}))
            time.sleep(10)

    threading.Thread(target=ping, daemon=True).start()

def on_message(wsapp, message):
    data = json.loads(message)
    print(data)

wsapp = websocket.WebSocketApp("wss://ws-subscriptions-clob.polymarket.com/ws/market", on_open=on_open, on_message=on_message)
wsapp.run_forever()



