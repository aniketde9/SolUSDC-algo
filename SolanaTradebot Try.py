import ccxt
import asyncio
import websockets
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime
import pandas_ta as ta_pandas
import ta

# Configure logging
logging.basicConfig(filename='trading_bot.log', level=logging.INFO, format='%(asctime)s - %(message)s')

# Initialize Binance API
binance = ccxt.binance({
    'apiKey': 'AppzE59Z1cF5pGUTmGcE2hxlI0oWa00TYhpD6PBj5EAW9cH2WpFflmXOH6EuWo5y',
    'secret': '11sfe1D2H9lYKrkQuHZC9n72kJErJNAZqL0oxwmPvsbAdcF6kNUBB47YYXqQQsjH',
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
        'adjustForTimeDifference': True,
    }
})

# Global Variables
symbol = 'SOL/USDC'
initial_balance_usdc = 0.0
compounding_balance_usdc = 0.0
trade_log = []

# Function to get the initial USDC balance
async def get_initial_balance():
    global initial_balance_usdc, compounding_balance_usdc
    balance = await binance.fetch_balance()
    initial_balance_usdc = balance['total']['USDC']
    compounding_balance_usdc = initial_balance_usdc
    logging.info(f"Initial USDC balance: {initial_balance_usdc}")
    print(f"Initial USDC balance: {initial_balance_usdc}")

# WebSocket connection for real-time data
async def binance_websocket():
    url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@depth"
    async with websockets.connect(url) as websocket:
        while True:
            response = await websocket.recv()
            data = json.loads(response)
            process_order_book(data)

# Process order book data
def process_order_book(data):
    global trade_log, compounding_balance_usdc

    # Extract the best bid and ask prices
    bids = data.get('bids', [])
    asks = data.get('asks', [])
    best_bid = float(bids[0][0]) if bids else None
    best_ask = float(asks[0][0]) if asks else None

    if best_bid and best_ask:
        logging.info(f"Best Bid: {best_bid}, Best Ask: {best_ask}")

        # Fetch historical prices and calculate indicators
        prices = get_historical_prices()
        indicators = calculate_indicators(prices)
        if indicators:
            signal, price, atr = dynamic_signal_generation(indicators, best_bid, best_ask)
            if signal:
                logging.info(f"{signal.capitalize()} signal generated at price: {price}")
                asyncio.create_task(execute_trade(signal, compounding_balance_usdc / price, price, atr))

# Fetch historical prices for indicator calculation
def get_historical_prices():
    # Fetch the last 100 one-minute candles
    ohlcv = binance.fetch_ohlcv(symbol, timeframe='1m', limit=100)
    prices = {
        'timestamp': [x[0] for x in ohlcv],
        'open': [x[1] for x in ohlcv],
        'high': [x[2] for x in ohlcv],
        'low': [x[3] for x in ohlcv],
        'close': [x[4] for x in ohlcv],
        'volume': [x[5] for x in ohlcv]
    }
    return prices

# Function to calculate technical indicators using pandas_ta and ta
def calculate_indicators(prices):
    close_prices = prices['close']
    high_prices = prices['high']
    low_prices = prices['low']

    if len(close_prices) > 14:  # Ensure enough data points for calculation
        rsi = ta.momentum.rsi(close_prices, window=14)
        bbands = ta.volatility.BollingerBands(close_prices, window=14, window_dev=2)
        macd = ta.trend.macd(close_prices)
        atr = ta.volatility.average_true_range(high_prices, low_prices, close_prices, window=14)
        return {
            'rsi': rsi,
            'upperband': bbands.bollinger_hband(),
            'middleband': bbands.bollinger_mavg(),
            'lowerband': bbands.bollinger_lband(),
            'macd': macd,
            'atr': atr
        }
    return {}

# Function to place orders
async def place_order(side, amount, price):
    for attempt in range(5):
        try:
            if side == 'buy':
                order = await binance.create_limit_buy_order(symbol, amount, price)
            else:
                order = await binance.create_limit_sell_order(symbol, amount, price)
            logging.info(f"Placed {side} order: {order}")
            return order
        except ccxt.BaseError as e:
            logging.error(f"API Error while placing order: {e}")
            await asyncio.sleep(2 ** attempt)
    logging.error("Failed to place order after 5 attempts")
    return None

# Function to execute trade based on signal
async def execute_trade(side, amount, price, atr):
    global compounding_balance_usdc, trade_log
    try:
        order = await place_order(side, amount, price)
        if order:
            logging.info(f"Order placed: {order}")
            # Wait for the order to be filled
            await asyncio.sleep(2)  # Simulating wait time for order to fill
            order_status = await binance.fetch_order(order['id'], symbol)
            if order_status['status'] == 'closed':
                filled_amount = order_status['filled']
                trade_log.append({
                    'timestamp': datetime.now(),
                    'side': side,
                    'amount': filled_amount,
                    'price': price,
                    'status': 'filled'
                })
                # Update compounding balance
                if side == 'buy':
                    compounding_balance_usdc -= filled_amount * price * (1 + binance.fees['trading']['maker'])
                    take_profit_price = price + (atr * 1.5)  # Example: Take profit at 1.5 ATR above the buy price
                    asyncio.create_task(place_order('sell', filled_amount, take_profit_price))
                elif side == 'sell':
                    compounding_balance_usdc += filled_amount * price * (1 - binance.fees['trading']['taker'])
                    take_profit_price = price - (atr * 1.5)  # Example: Take profit at 1.5 ATR below the sell price
                    asyncio.create_task(place_order('buy', filled_amount, take_profit_price))
                logging.info(f"Updated compounding balance: {compounding_balance_usdc}")
            else:
                logging.info(f"Order not filled: {order_status}")
    except Exception as e:
        logging.error(f"Error executing trade: {e}")

# Improved main function with balance update and logging
async def main():
    await get_initial_balance()
    asyncio.create_task(binance_websocket())
    while True:
        await update_balance()  # Periodically update balance
        log_trades_to_file()  # Save trade log periodically
        await asyncio.sleep(60)  # Adjust sleep time for balance updates and logging

if __name__ == '__main__':
    asyncio.run(main())

# Enhanced balance update with safety checks
async def update_balance():
    global compounding_balance_usdc, initial_balance_usdc
    try:
        balance = await binance.fetch_balance()
        current_usdc_balance = balance['total']['USDC']
        # Ensure only initial balance is used for trading
        compounding_balance_usdc = min(compounding_balance_usdc, current_usdc_balance)
        logging.info(f"Updated USDC balance: {current_usdc_balance}, Compounding balance: {compounding_balance_usdc}")
    except Exception as e:
        logging.error(f"Error fetching balance: {e}")

# Save trade logs to a file periodically
def log_trades_to_file():
    try:
        df = pd.DataFrame(trade_log)
        df.to_csv('trade_log.csv', index=False)
        logging.info("Trade log saved to trade_log.csv")
    except Exception as e:
        logging.error(f"Error saving trade log to file: {e}")

# Improved order book processing with detailed signal generation
def process_order_book(data):
    global trade_log, compounding_balance_usdc

    # Extract the best bid and ask prices
    bids = data.get('bids', [])
    asks = data.get('asks', [])
    best_bid = float(bids[0][0]) if bids else None
    best_ask = float(asks[0][0]) if asks else None

    if best_bid and best_ask:
        logging.info(f"Best Bid: {best_bid}, Best Ask: {best_ask}")

        # Fetch historical prices and calculate indicators
        prices = get_historical_prices()
        indicators = calculate_indicators(prices)
        if indicators:
            signal, price, atr = dynamic_signal_generation(indicators, best_bid, best_ask)
            if signal:
                logging.info(f"{signal.capitalize()} signal generated at price: {price}")
                asyncio.create_task(execute_trade(signal, compounding_balance_usdc / price, price, atr))

# Signal generation logic based on technical indicators
def dynamic_signal_generation(indicators, best_bid, best_ask):
    current_rsi = indicators['rsi'].iloc[-1]
    lower_band = indicators['lowerband'].iloc[-1]
    upper_band = indicators['upperband'].iloc[-1]
    macd = indicators['macd'].iloc[-1]
    atr = indicators['atr'].iloc[-1]

    # Dynamic thresholds for buy/sell signals
    buy_threshold_rsi = 30
    sell_threshold_rsi = 70

    # Adjust thresholds based on market conditions and additional indicators
    if current_rsi < buy_threshold_rsi and best_ask <= lower_band and macd > 0:
        return 'buy', best_ask, atr
    elif current_rsi > sell_threshold_rsi and best_bid >= upper_band and macd < 0:
        return 'sell', best_bid, atr
    return None, None, None

# Error handling for WebSocket connection
async def binance_websocket():
    url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@depth"
    while True:
        try:
            async with websockets.connect(url) as websocket:
                while True:
                    response = await websocket.recv()
                    data = json.loads(response)
                    process_order_book(data)
        except (websockets.ConnectionClosed, websockets.InvalidStatusCode) as e:
            logging.error(f"WebSocket error: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)  # Wait and retry connection

# Function to log trades to a file
def log_trades_to_file():
    try:
        df = pd.DataFrame(trade_log)
        df.to_csv('trade_log.csv', index=False)
        logging.info("Trade log saved to trade_log.csv")
    except Exception as e:
        logging.error(f"Error saving trade log to file: {e}")

# Graceful shutdown handling
def handle_exit(signum, frame):
    logging.info("Shutting down the bot...")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.sleep(1))
    loop.close()
    exit(0)

# Signal handling for graceful shutdown
import signal
signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
