import requests
import json

'''
slugs = ["balance-of-power-2026-midterms", "democratic-presidential-nominee-2028", "presidential-election-winner-2028", "fed-decision-in-april"]
ids = []
def GetEvents():
    for id in slugs:
        url = f"https://gamma-api.polymarket.com/events/slug/{id}"
        r = requests.get(url)
        output = r.json()[""]
        print(output)
        ids.extend(output)
    return print(ids)

GetEvents()
'''

def GetEvents():
    url = "https://gamma-api.polymarket.com/events/slug/balance-of-power-2026-midterms"
    r = requests.get(url)
    data = r.json()
    print(json.dumps(data, indent=2))
    for slug, value in data["markets"].items():
        slug = value["slug"]
        print(slug)


    return None

GetEvents()

