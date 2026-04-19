from py_clob_client.client import ClobClient

client = ClobClient(
    "https://clob.polymarket.com",
    key="",  # your wallet private key
    chain_id=137             # polygon mainnet
)

api_creds = client.create_api_key()
print(api_creds)