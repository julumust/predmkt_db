# Database Library 
Python library for - exclusively crypto up-down - market data collection

## Documentation

### Installation 
```
git clone https://github.com/julumust/predmkt_db.git
```

### Quickstart


```python
crypto = GetCryptoID(["btc","eth","sol"]) # This list can change according to your interests e.g. GetCryptoID(["btc"])
handler = WebSocketHandler(crypto)
handler.start()
```
### Polymarket ```GetCryptoID()```

#### Current market ```assets_ids``` function 
Exclusively for 5 minute crypto markets on Polymarket, future development would integrate 15 minute markets.

```python
def get_assetID(self): # Retrieves current clobTokenID through current market slug
  now = int(time.time())
  current_boundary = (now // 300) * 300 # UNIX Timestamp associated with slug e.g. btc-updown-5m-{1775661900}
  self.token = []
  for i in self.tickers:
    slug = f"{i}-updown-5m-{current_boundary}"
    r = requests.get("https://gamma-api.polymarket.com/markets", params={"slug": slug})
    raw_ids = r.json()[0]["clobTokenIds"]
    parsed_ids = json.loads(raw_ids)
    self.token.extend(parsed_ids)
return self.token
```

#### Future market ```assets_ids``` function 
Functionally the same ```get_assetID()``` retrieves future market UNIX timestamp.

```python
def get_updatedID(self): # Retrieves future market clobTokenID by retrieving next market slug
  now = int(time.time())
  next_boundary = (now // 300 + 1) * 300 # UNIX Timestamp associated with slug e.g. btc-updown-5m-{1775661900}
  self.token = []
  for i in self.tickers:
    slug = f"{i}-updown-5m-{next_boundary}"
    r = requests.get("https://gamma-api.polymarket.com/markets", params={"slug": slug})
    raw_ids = r.json()[0]["clobTokenIds"]
    parsed_ids = json.loads(raw_ids)
    self.token.extend(parsed_ids)
return self.token
```
### Polymarket ```WebSocketHandler()```

#### Market Subscription ```schedule_rotation()```

Market slugs change according to the market duration, the function below, maintains a continous stream of data despite that change.

```python
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
```


## Kalshi Websocket Library

Work in progress...
