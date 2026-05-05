import requests
import json

url = "https://gamma-api.polymarket.com/events/slug/epl-mun-bre-2026-04-27"

def teams():
    data = requests.get(url)
    parsed_data = data.json()
    output = json.dumps(parsed_data, indent=1)
    return print(output)

teams()
