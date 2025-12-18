import asyncio
import sys
import argparse
import os
from decimal import Decimal
import dotenv

# 导入策略和交易所类
from strategy.edgex_arb import EdgexArb
from exchanges.edgex import EdgeXExchange
from exchanges.lighter import LighterExchange
from exchanges.paradex import ParadexExchange

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Cross-Exchange Arbitrage Bot Entry Point',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--exchange', type=str, default='paradex',
                        help='Exchange to use as Maker (edgex or paradex)')
    parser.add_argument('--ticker', type=str, default='BTC',
                        help='Ticker symbol (default: BTC)')
    parser.add_argument('--size', type=str, required=True,
                        help='Number of tokens to buy/sell per order')
    parser.add_argument('--fill-timeout', type=int, default=5,
                        help='Timeout in seconds for maker order fills (default: 5)')
    parser.add_argument('--max-position', type=Decimal, default=Decimal('0'),
                        help='Maximum position to hold (default: 0)')
    parser.add_argument('--long-threshold', type=Decimal, default=Decimal('10'),
                        help='Long threshold for price difference (default: 10)')
    parser.add_argument('--short-threshold', type=Decimal, default=Decimal('10'),
                        help='Short threshold for price difference (default: 10)')
    return parser.parse_args()

def validate_exchange(exchange):
    supported_exchanges = ['edgex', 'paradex']
    if exchange.lower() not in supported_exchanges:
        print(f"Error: Unsupported exchange '{exchange}'")
        print(f"Supported exchanges: {', '.join(supported_exchanges)}")
        sys.exit(1)

async def main():
    args = parse_arguments()
    dotenv.load_dotenv()
    validate_exchange(args.exchange)

    try:
        # 1. 初始化 Maker 交易所
        if args.exchange.lower() == 'paradex':
            maker_ex = ParadexExchange(
                account_address=os.getenv("PARADEX_ACCOUNT_ADDRESS"),
                private_key=os.getenv("PARADEX_PRIVATE_KEY")
            )
            print("Successfully initialized Paradex as Maker exchange.")
        else:
            maker_ex = EdgeXExchange(
                account_id=os.getenv("EDGEX_ACCOUNT_ID"),
                stark_private_key=os.getenv("EDGEX_STARK_PRIVATE_KEY")
            )
            print("Successfully initialized EdgeX as Maker exchange.")

        # 2. 初始化 Taker 交易所 (Lighter)
        taker_ex = LighterExchange(
            api_key_private_key=os.getenv("API_KEY_PRIVATE_KEY"),
            account_index=int(os.getenv("LIGHTER_ACCOUNT_INDEX", 0)),
            api_key_index=int(os.getenv("LIGHTER_API_KEY_INDEX", 0))
        )

        # 3. 启动策略
        bot = EdgexArb(
            ticker=args.ticker.upper(),
            order_quantity=Decimal(args.size),
            fill_timeout=args.fill_timeout,
            max_position=args.max_position,
            long_ex_threshold=Decimal(args.long_threshold),
            short_ex_threshold=Decimal(args.short_threshold),
            maker_ex=maker_ex, 
            taker_ex=taker_ex  
        )

        print(f"Starting arbitrage on {args.ticker} between {args.exchange} and Lighter...")
        await bot.run()

    except KeyboardInterrupt:
        print("\nCross-Exchange Arbitrage interrupted by user")
    except Exception as e:
        print(f"Error during execution: {e}")
        return 1

if __name__ == "__main__":
    asyncio.run(main())
