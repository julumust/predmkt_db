from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BookParams
from polymarket.market import GetCryptoID, WebSocketHandler


'''
HOST = "https://clob.polymarket.com"
CHAIN_ID = 137 # Polygon chain ID (137)
PRIVATE_KEY = "<your-privatekey>"
FUNDER = "<your-funder-address>"

client = ClobClient(
    HOST, # The clob API endpoint
    key = PRIVATE_KEY, # Your wallet's private key
    chain_id = CHAIN_ID, # Polygon chain ID (137)
    signature_type = 1, # Informs system on signature verification protocols: 0, 1, and 2
    funder = FUNDER
)
'''

crypto = GetCryptoID(["btc","eth","sol"])
handler = WebSocketHandler(crypto)
handler.start()


