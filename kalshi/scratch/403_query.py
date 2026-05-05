import requests
from market import KalshiAuth, base_url, access_key, auth

a = KalshiAuth(BASE_URL=base_url, AUTH=auth, ACCESS_KEY=access_key)
path = "/trade-api/v2/portfolio/balance"
r = requests.get(
    f"https://api.elections.kalshi.com{path}",
    headers=a.headers(method="GET", path=path),
)
print(r.status_code, r.text)