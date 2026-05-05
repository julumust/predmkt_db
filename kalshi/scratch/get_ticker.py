import requests
import json
import time


## Slug example: kxbtc15m-26jan110930
## Date changes, timestamp changes
## Design a function that handles both
## Start with timestamp...

class Ticker:
    def __init__(self, series_ticker: str) -> str:
        self.series_ticker = series_ticker

    def get_ticker(self):
        url = f"https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker={self.series_ticker}&status=open"
        data = requests.get(url).json()
        for item in data["markets"]:
            ticker = item.get("ticker")
        return print(ticker)
    
    
x = Ticker(series_ticker="KXBTC15M")
x.get_ticker()