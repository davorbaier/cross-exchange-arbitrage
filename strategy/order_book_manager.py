class OrderBookManager:
    def __init__(self, maker_ex, taker_ex, ticker):
        self.maker_ex = maker_ex
        self.taker_ex = taker_ex
        self.ticker = ticker
        self.maker_book = None
        self.taker_book = None

    async def start(self):
        # 启动异步任务同时获取两端深度
        asyncio.create_task(self._update_maker_book())
        asyncio.create_task(self._update_taker_book())

    async def _update_maker_book(self):
        while True:
            # 关键：这里会自动调用你传入的 ParadexExchange.get_orderbook
            self.maker_book = await self.maker_ex.get_orderbook(self.ticker)
            await asyncio.sleep(0.1)

    async def _update_taker_book(self):
        while True:
            self.taker_book = await self.taker_ex.get_orderbook(self.ticker)
            await asyncio.sleep(0.1)

    def get_maker_book(self): return self.maker_book
    def get_taker_book(self): return self.taker_book
