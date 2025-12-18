import asyncio
import logging
from decimal import Decimal
from .order_manager import OrderManager
from .position_tracker import PositionTracker
from .order_book_manager import OrderBookManager
from .data_logger import DataLogger

class EdgexArb:
    def __init__(self, ticker, order_quantity, fill_timeout, max_position, 
                 long_ex_threshold, short_ex_threshold, maker_ex, taker_ex):
        self.ticker = ticker
        self.order_quantity = Decimal(str(order_quantity))
        self.fill_timeout = fill_timeout
        self.max_position = Decimal(str(max_position))
        self.long_threshold = Decimal(str(long_ex_threshold))
        self.short_threshold = Decimal(str(short_ex_threshold))

        # 现在使用从外部传入的交易所对象
        self.maker_ex = maker_ex
        self.taker_ex = taker_ex

        # 初始化辅助模块
        self.order_manager = OrderManager(self.maker_ex, self.taker_ex)
        self.position_tracker = PositionTracker(self.maker_ex, self.taker_ex, ticker)
        self.order_book_manager = OrderBookManager(self.maker_ex, self.taker_ex, ticker)
        self.data_logger = DataLogger(ticker)

        self.logger = logging.getLogger(__name__)

    async def run(self):
        """主循环：监控价格并执行套利"""
        self.logger.info(f"开始套利监控: {self.ticker}")
        
        # 启动 WebSocket 监听
        await asyncio.gather(
            self.order_book_manager.start(),
            self.position_tracker.start_tracking()
        )

        while True:
            try:
                # 获取两端实时价格
                maker_book = self.order_book_manager.get_maker_book()
                taker_book = self.order_book_manager.get_taker_book()

                if not maker_book or not taker_book:
                    await asyncio.sleep(0.1)
                    continue

                # 这里的逻辑会自动适配 Paradex 或 EdgeX，因为它们共用了相同的接口
                await self.check_arbitrage_opportunity(maker_book, taker_book)
                
                await asyncio.sleep(0.01) # 极短延迟以防阻塞
            except Exception as e:
                self.logger.error(f"策略运行异常: {e}")
                await asyncio.sleep(1)

    async def check_arbitrage_opportunity(self, maker_book, taker_book):
        # 示例逻辑：当 Taker(Lighter) 卖一价 - Maker(Paradex) 买一价 > 阈值时，做多 Maker
        maker_bid = Decimal(str(maker_book['bids'][0][0]))
        taker_ask = Decimal(str(taker_book['asks'][0][0]))
        
        if (taker_ask - maker_bid) > self.long_threshold:
            self.logger.info(f"发现机会！价差: {taker_ask - maker_bid}")
            # 执行 Maker 挂单逻辑
            await self.order_manager.place_maker_order(
                self.ticker, "BUY", maker_bid, self.order_quantity, self.fill_timeout
            )
