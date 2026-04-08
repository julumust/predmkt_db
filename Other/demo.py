import requests 
import time
import json
'''
def get_assetID(): # Fetches current slug for btc-updown-5m
    now = int(time.time())
    current_boundary = (now // 300) * 300
    slug = f"btc-updown-5m-{current_boundary}"
    r = requests.get("https://gamma-api.polymarket.com/markets", params={"slug": slug})
    return json.loads(r.json()[0]["clobTokenIds"])
'''

def get_assetID():
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

'''
def get_updatedID():
    now = int(time.time())
    next_boundary = (now // 300 + 1) * 300
    slug = f"btc-updown-5m-{next_boundary}"
    r = requests.get("https://gamma-api.polymarket.com/markets", params={"slug": slug})
    return r.json()[0]["clobTokenIds"]
'''

def get_updatedID(): # Fetches slug for future 
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

x = get_assetID()
print("Current:", x)