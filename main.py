from polymarket.market import GetCryptoID, WebSocketHandler

retrieve_ID = GetCryptoID(["btc"])
handler = WebSocketHandler(retrieve_ID)
handler.start()

