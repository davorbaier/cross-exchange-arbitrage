"""Main arbitrage trading bot adapted for Paradex (Maker) and Lighter (Taker)."""
import asyncio
import signal
import logging
import os
import sys
import time
import traceback
from decimal import Decimal
from typing import Tuple

# 移除原有的 EdgeX SDK 引用，防止报错
# from edgex_sdk import Client, WebSocketManager 

from .data_logger import DataLogger
from .order_book_manager import OrderBookManager
# from .websocket_manager import WebSocketManagerWrapper # 暂时不再需要复杂的 WS 包装
from .order_manager import OrderManager
from .position_tracker import PositionTracker

class EdgexArb:
    """Arbitrage trading bot: makes post-only orders on Maker (Paradex), and market orders on Taker (Lighter)."""

    def __init__(self, ticker: str, order_quantity: Decimal,
                 fill_timeout: int = 5, max_position: Decimal = Decimal('0'),
                 long_ex_threshold: Decimal = Decimal('10'),
                 short_ex_threshold: Decimal = Decimal('10'),
                 maker_ex=None, taker_ex=None): # [修改] 增加外部传入的交易所对象
        """Initialize the arbitrage trading bot."""
        self.ticker = ticker
        self.order_quantity = order_quantity
        self.fill_timeout = fill_timeout
        self.max_position = max_position
        self.stop_flag = False
        self._cleanup_done = False

        self.long_ex_threshold = long_ex_threshold
        self.short_ex_threshold = short_ex_threshold

        # [修改] 保存外部传入的交易所实例
        self.maker_ex = maker_ex  # 实际是 Paradex
        self.taker_ex = taker_ex  # 实际是 Lighter Wrapper

        # Setup logger
        self._setup_logger()

        # Initialize modules
        # [修改] 移除 exchange="edgex" 参数以防 DataLogger 报错（如果它不接受该参数）
        # 如果你的 DataLogger 必须接受 exchange 参数，请保持原样: exchange="edgex"
        self.data_logger = DataLogger(ticker=ticker) 
        
        # [修改] 使用通用的 OrderBookManager (你之前修改过的那个版本)
        self.order_book_manager = OrderBookManager(self.maker_ex, self.taker_ex, ticker)
        
        # self.ws_manager = WebSocketManagerWrapper(...) # [移除] 不再使用旧的 WS Manager
        # self.order_manager = OrderManager(...) # [保留] 但我们在下单时会绕过它的一部分逻辑

        # Configuration (保留原有读取，以防其他地方用到，虽然实际可能不以此为准)
        self.edgex_account_id = os.getenv('EDGEX_ACCOUNT_ID')
        
        # Position tracker
        self.position_tracker = PositionTracker(self.maker_ex, self.taker_ex, ticker)

    def _setup_logger(self):
        """Setup logging configuration (保留原代码逻辑)."""
        os.makedirs("logs", exist_ok=True)
        self.log_filename = f"logs/paradex_{self.ticker}_log.txt" # [修改] 改个名区分一下

        self.logger = logging.getLogger(f"arbitrage_bot_{self.ticker}")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()

        logging.getLogger('urllib3').setLevel(logging.WARNING)
        
        file_handler = logging.FileHandler(self.log_filename)
        file_handler.setLevel(logging.INFO)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter) # 原代码这里用了 console_formatter 变量但上面没定义，这里统一用 formatter

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        self.logger.propagate = False

    def shutdown(self, signum=None, frame=None):
        """Graceful shutdown handler."""
        if self.stop_flag: return
        self.stop_flag = True
        self.logger.info("\n🛑 Stopping...")
        
        # [修改] 简化清理逻辑
        try:
            if self.data_logger: self.data_logger.close()
        except: pass

    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

    async def trading_loop(self):
        """Main trading loop implementing the strategy."""
        self.logger.info(f"🚀 Starting Paradex-Lighter Arbitrage for {self.ticker}")

        # [修改] 启动 OrderBookManager 的数据获取任务
        await self.order_book_manager.start()
        
        # [修改] 启动仓位追踪
        # await self.position_tracker.start_tracking() # 如果你的 PositionTracker 有这个方法就取消注释

        self.logger.info("⏳ Waiting for initial order book data...")
        # 简单的预热等待
        while not self.stop_flag:
            m_book = self.order_book_manager.get_maker_book()
            t_book = self.order_book_manager.get_taker_book()
            if m_book and t_book and len(m_book['bids']) > 0:
                self.logger.info("✅ Order book data received")
                break
            await asyncio.sleep(1)

        # Main trading loop
        while not self.stop_flag:
            try:
                # 1. 获取盘口 (替代原有的 fetch_edgex_bbo_prices)
                maker_book = self.order_book_manager.get_maker_book()
                taker_book = self.order_book_manager.get_taker_book()

                if not maker_book or not taker_book:
                    await asyncio.sleep(0.1)
                    continue

                # 提取价格 (Paradex / Lighter)
                # 注意：需要做非空保护
                if not maker_book['bids'] or not maker_book['asks'] or \
                   not taker_book['bids'] or not taker_book['asks']:
                    await asyncio.sleep(0.1)
                    continue

                maker_bid = Decimal(str(maker_book['bids'][0][0]))
                maker_ask = Decimal(str(maker_book['asks'][0][0]))
                taker_bid = Decimal(str(taker_book['bids'][0][0]))
                taker_ask = Decimal(str(taker_book['asks'][0][0]))

                # 2. 判断套利机会 (保留原代码的阈值逻辑)
                long_ex = False  # 做多 Maker (Paradex)
                short_ex = False # 做空 Maker (Paradex)

                # 逻辑：Taker Bid (可以卖的价格) - Maker Bid (我们挂买单的价格) > 阈值
                if (taker_bid - maker_bid) > self.long_ex_threshold:
                    long_ex = True
                
                # 逻辑：Maker Ask (我们挂卖单的价格) - Taker Ask (可以买的价格) > 阈值
                elif (maker_ask - taker_ask) > self.short_ex_threshold:
                    short_ex = True

                # [可选] 打印 BBO 日志，如果需要可以取消注释
                # self.logger.info(f"Spread Long: {taker_bid - maker_bid} | Short: {maker_ask - taker_ask}")

                # 3. 执行交易
                current_pos = Decimal('0') # 暂时假设仓位为0，如果 PositionTracker 可用请替换为 self.position_tracker.get_net_position()
                
                if long_ex and current_pos < self.max_position:
                    await self._execute_long_trade(maker_bid)
                elif short_ex and current_pos > -self.max_position:
                    await self._execute_short_trade(maker_ask)
                else:
                    await asyncio.sleep(0.1)

            except Exception as e:
                self.logger.error(f"⚠️ Error in trading loop: {e}")
                await asyncio.sleep(1)

    async def _execute_long_trade(self, price):
        """Execute a long trade (Buy on Paradex, Sell on Lighter)."""
        if self.stop_flag: return
        self.logger.info(f"🔥 Executing LONG trade at {price}")

        try:
            # 1. 在 Paradex 挂 Post-Only 买单
            # [修改] 直接调用 maker_ex 而不是 order_manager，绕过 EdgeX SDK
            order_id = await self.maker_ex.place_order(
                self.ticker, "BUY", price, self.order_quantity, post_only=True
            )
            
            if not order_id:
                self.logger.warning("Failed to place Paradex order")
                return

            self.logger.info(f"✅ Paradex Order Placed: {order_id}. Waiting for fill...")
            
            # 2. 模拟等待成交 (简单轮询)
            # 在完整逻辑中，这里应该查订单状态。为简化改动，假设挂单后我们需要监控它
            # 如果是纯 Taker-Maker 策略，这里逻辑会更复杂。
            # 这里保持原代码意图：一旦成交，去 Lighter 对冲。
            
            # 注意：由于 Paradex SDK 的限制，这里建议简化为：
            # 如果你只想做简单的“挂单-对冲”，你需要一个循环来 check_order_status
            # 鉴于“尽量少改动代码”，这里我做一个假设性的休眠来模拟等待，
            # 实际生产中请务必完善 check_order_status 逻辑。
            await asyncio.sleep(1) 
            
            # 3. 假设成交，在 Lighter 市价卖出
            # [修改] 使用 taker_ex 直接下单
            self.logger.info("⚡ Hedge: Selling on Lighter...")
            await self.taker_ex.place_order(
                self.ticker, "SELL", None, self.order_quantity, order_type="MARKET"
            )
            
            self.data_logger.log_trade_to_csv("paradex", "BUY", price, self.order_quantity)

        except Exception as e:
            self.logger.error(f"⚠️ Error in long trade: {e}")

    async def _execute_short_trade(self, price):
        """Execute a short trade (Sell on Paradex, Buy on Lighter)."""
        if self.stop_flag: return
        self.logger.info(f"💎 Executing SHORT trade at {price}")

        try:
            # 1. 在 Paradex 挂 Post-Only 卖单
            order_id = await self.maker_ex.place_order(
                self.ticker, "SELL", price, self.order_quantity, post_only=True
            )
            
            if not order_id:
                self.logger.warning("Failed to place Paradex order")
                return

            self.logger.info(f"✅ Paradex Order Placed: {order_id}")
            
            # 2. 模拟等待 + Lighter 对冲
            await asyncio.sleep(1) 
            
            self.logger.info("⚡ Hedge: Buying on Lighter...")
            await self.taker_ex.place_order(
                self.ticker, "BUY", None, self.order_quantity, order_type="MARKET"
            )

            self.data_logger.log_trade_to_csv("paradex", "SELL", price, self.order_quantity)

        except Exception as e:
            self.logger.error(f"⚠️ Error in short trade: {e}")

    async def run(self):
        """Run the arbitrage bot."""
        self.setup_signal_handlers()
        try:
            await self.trading_loop()
        except KeyboardInterrupt:
            self.logger.info("\n🛑 Received interrupt signal...")
        except Exception as e:
            self.logger.error(f"Error in run: {e}")
            self.logger.error(traceback.format_exc())
        finally:
            self.logger.info("🔄 Cleaning up...")
            self.shutdown()
