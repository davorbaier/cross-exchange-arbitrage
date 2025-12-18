import asyncio
from .base import Exchange
# 注意：在服务器部署时需确保安装了 paradex-py
try:
    from paradex_py import ParadexClient
except ImportError:
    ParadexClient = None

class ParadexExchange(Exchange):
    def __init__(self, account_address, private_key, env="prod"):
        self.name = "paradex"
        self.account_address = account_address
        self.private_key = private_key
        # 初始化 Paradex 客户端
        self.client = ParadexClient(
            env=env, 
            account_address=account_address, 
            private_key=private_key
        )
        self.symbol_map = {"BTC": "BTC-USD-PERP", "ETH": "ETH-USD-PERP"}

    async def get_orderbook(self, ticker):
        symbol = self.symbol_map.get(ticker, f"{ticker}-USD-PERP")
        # 获取 L2 订单簿
        response = await self.client.get_orderbook(symbol)
        return {
            "bids": [[float(i[0]), float(i[1])] for i in response.get('bids', [])],
            "asks": [[float(i[0]), float(i[1])] for i in response.get('asks', [])]
        }

    async def place_order(self, ticker, side, price, size, order_type="LIMIT", post_only=True):
        symbol = self.symbol_map.get(ticker, f"{ticker}-USD-PERP")
        params = {
            "market": symbol,
            "side": side.upper(),
            "type": order_type,
            "size": str(size),
        }
        if order_type == "LIMIT":
            params["price"] = str(price)
            if post_only:
                params["instruction"] = "POST_ONLY"
        
        return await self.client.create_order(**params)

    async def get_position(self, ticker):
        symbol = self.symbol_map.get(ticker, f"{ticker}-USD-PERP")
        positions = await self.client.get_positions()
        for p in positions:
            if p['market'] == symbol:
                return float(p['size'])
        return 0.0
