import asyncio
from .base import Exchange

# 确保服务器未安装 paradex-py 时不会直接崩溃，而是提示警告
try:
    from paradex_py import ParadexClient
except ImportError:
    ParadexClient = None
    print("Warning: paradex-py not installed. Paradex functionality will be disabled.")

class ParadexExchange(Exchange):
    def __init__(self, account_address, private_key, env="prod"):
        self.name = "paradex"
        self.account_address = account_address
        self.private_key = private_key
        
        if ParadexClient:
            self.client = ParadexClient(
                env=env, 
                account_address=account_address, 
                private_key=private_key
            )
        else:
            self.client = None
            
        # 交易对映射 (可根据需要扩展)
        self.symbol_map = {"BTC": "BTC-USD-PERP", "ETH": "ETH-USD-PERP"}

    async def get_orderbook(self, ticker):
        if not self.client: return {"bids": [], "asks": []}
        
        symbol = self.symbol_map.get(ticker, f"{ticker}-USD-PERP")
        try:
            # 获取 L2 订单簿
            response = await self.client.get_orderbook(symbol)
            # 关键：Paradex 返回字符串，必须转 float
            return {
                "bids": [[float(i[0]), float(i[1])] for i in response.get('bids', [])],
                "asks": [[float(i[0]), float(i[1])] for i in response.get('asks', [])]
            }
        except Exception as e:
            print(f"Error fetching Paradex orderbook: {e}")
            return {"bids": [], "asks": []}

    async def place_order(self, ticker, side, price, size, order_type="LIMIT", post_only=True):
        if not self.client: return None

        symbol = self.symbol_map.get(ticker, f"{ticker}-USD-PERP")
        params = {
            "market": symbol,
            "side": side.upper(), # 必须大写
            "type": order_type,
            "size": str(size),    # SDK 要求字符串
        }
        
        if order_type == "LIMIT":
            params["price"] = str(price) # SDK 要求字符串
            if post_only:
                params["instruction"] = "POST_ONLY"
        
        return await self.client.create_order(**params)

    async def get_position(self, ticker):
        if not self.client: return 0.0

        symbol = self.symbol_map.get(ticker, f"{ticker}-USD-PERP")
        try:
            positions = await self.client.get_positions()
            for p in positions:
                if p['market'] == symbol:
                    return float(p['size'])
        except Exception:
            pass
        return 0.0
