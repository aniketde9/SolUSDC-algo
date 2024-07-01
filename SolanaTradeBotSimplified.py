import ccxt
import asyncio
import logging
import pandas as pd
import numpy as np
from datetime import datetime
import ta
import pygame
import time


# Configure logging
logging.basicConfig(filename='Soltradebot.log', level=logging.INFO, format='%(asctime)s - %(message)s')

# Initialize Binance API
binance = ccxt.binance({
    'apiKey': 'AppzE59Z1cF5pGUTmGcE2hxlI0oWa00TYhpD6PBj5EAW9cH2WpFflmXOH6EuWo5y',
    'secret': '11sfe1D2H9lYKrkQuHZC9n72kJErJNAZqL0oxwmPvsbAdcF6kNUBB47YYXqQQsjH',
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
        'adjustForTimeDifference': True,
        'recvWindow': 60000,
    }
})

# Synchronize with Binance server time
def synchronize_time():
    server_time = binance.fetch_time()
    local_time = int(datetime.now().timestamp() * 1000)
    binance.options['adjustForTimeDifference'] = True
    binance.options['timeDifference'] = server_time - local_time
    logging.info(f"Synchronized server time. Server time: {server_time}, Local time: {local_time}, Time difference: {binance.options['timeDifference']}")

# Global Variables
symbol = 'SOL/USDC'
usdc_balance = 0.0
sol_balance = 0.0
minimum_amount = 0.001
trade_log = []
maker_fee = 0.00075  # Maker fee
taker_fee = 0.0007125  # Taker fee

# Function to get the initial USDC balance
async def get_initial_balance():
    global usdc_balance, sol_balance
    balance = binance.fetch_balance()
    usdc_balance = balance['total']['USDC']
    sol_balance = balance['total']['SOL']
    logging.info(f"Initial USDC balance: {usdc_balance}")
    logging.info(f"Initial SOL balance: {sol_balance}")
    print(f"Initial USDC balance: {usdc_balance}")
    print(f"Initial SOL balance: {sol_balance}")

# Fetch historical prices for indicator calculation
def get_historical_prices():
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

# Function to calculate technical indicators using ta
def calculate_indicators(prices):
    close_prices = pd.Series(prices['close'])
    high_prices = pd.Series(prices['high'])
    low_prices = pd.Series(prices['low'])

    rsi = ta.momentum.RSIIndicator(close=close_prices, window=14).rsi()
    macd = ta.trend.MACD(close=close_prices)
    macd_line = macd.macd()
    macd_signal = macd.macd_signal()
    bb = ta.volatility.BollingerBands(close=close_prices, window=20, window_dev=2)
    atr = ta.volatility.AverageTrueRange(high=high_prices, low=low_prices, close=close_prices, window=14).average_true_range()

    indicators = {
        'timestamp': datetime.now(),
        'rsi': rsi.iloc[-1],
        'macd_line': macd_line.iloc[-1],
        'macd_signal': macd_signal.iloc[-1],
        'bb_upper': bb.bollinger_hband().iloc[-1],
        'bb_lower': bb.bollinger_lband().iloc[-1],
        'atr': atr.iloc[-1]
    }
    return indicators

# Function to place orders
async def place_order(side, amount, price):
    for attempt in range(5):
        try:
            synchronize_time()  # Synchronize time before making the API call
            if side == 'buy':
                order = binance.create_limit_buy_order(symbol, amount, price)
            else:
                order = binance.create_limit_sell_order(symbol, amount, price)
            logging.info(f"Placed {side} order: {order}")
            return order
        except ccxt.BaseError as e:
            logging.error(f"API Error while placing order: {e}")
            await asyncio.sleep(2 ** attempt)
    logging.error("Failed to place order after 5 attempts")
    return None

# Function to replace open orders if certain conditions are met
async def replace_order(order_id, side, amount, new_price):
    try:
        synchronize_time()  # Synchronize time before making the API call
        binance.cancel_order(order_id, symbol)
        logging.info(f"Canceled open order: {order_id}")
        return await place_order(side, amount, new_price)
    except ccxt.BaseError as e:
        logging.error(f"API Error while replacing order: {e}")
    return None

# Dynamic signal generation logic
def dynamic_signal_generation(indicators, market_price):
    rsi = indicators['rsi']
    macd_line = indicators['macd_line']
    macd_signal = indicators['macd_signal']
    bb_upper = indicators['bb_upper']
    bb_lower = indicators['bb_lower']
    atr = indicators['atr']

    logging.info(f"RSI: {rsi}, MACD Line: {macd_line}, MACD Signal: {macd_signal}, BB Upper: {bb_upper}, BB Lower: {bb_lower}, ATR: {atr}")

    buy_signal = (macd_line > macd_signal and 25 < rsi < 45 and market_price <= bb_lower * 1.07)
    sell_signal = (macd_line < macd_signal and 75 > rsi > 55 and market_price >= bb_upper * 0.90)

    if buy_signal:
        return 'buy', market_price, atr
    elif sell_signal:
        return 'sell', market_price, atr
    return None, None, None

# Function to execute trade based on signal
async def execute_trade(signal, amount, price, atr, indicators):
    global usdc_balance, sol_balance, trade_log
    try:
        # Fetch the updated balance before placing orders
        await update_balance()

        # Adjust trade amount to ensure compliance with minimum amount and available balance
        if signal == 'buy':
            trade_amount = usdc_balance / (price * (1 + maker_fee))
            if trade_amount < minimum_amount:
                logging.warning(f"Insufficient USDC balance to buy minimum amount of SOL. Required: {minimum_amount} SOL")
                return
        else:
            trade_amount = sol_balance
            # Ensure trade amount meets the minimum amount
            if trade_amount < minimum_amount:
                logging.warning(f"Trade amount {trade_amount} SOL does not meet the minimum requirements")
                return

            # Include taker fees in the profit calculation
            effective_sold_amount = trade_amount * (1 - taker_fee)
            profit = effective_sold_amount * price - usdc_balance
            if profit <= 0:
                logging.warning(f"No profit would be made after fees. Trade amount: {trade_amount}, Effective sold amount: {effective_sold_amount}, Profit: {profit}")
                return

        order = await place_order(signal, trade_amount, price)
        if order:
            logging.info(f"Order placed: {order}")
            await asyncio.sleep(2)
            order_status = binance.fetch_order(order['id'], symbol)
            market_price = binance.fetch_ticker(symbol)['last']  # Fetch the latest market price
            if order_status['status'] == 'open':
                # Implement logic to replace the open order if certain conditions are met
                if signal == 'buy' and market_price < order['price'] * 0.98:
                    logging.info(f"Replacing buy order due to price drop: Order Price: {order['price']}, Market Price: {market_price}")
                    await replace_order(order['id'], signal, trade_amount, market_price)
                elif signal == 'sell' and market_price > order['price'] * 1.02:
                    logging.info(f"Replacing sell order due to price rise: Order Price: {order['price']}, Market Price: {market_price}")
                    await replace_order(order['id'], signal, trade_amount, market_price)
            elif order_status['status'] == 'closed':
                filled_amount = order_status['filled']
                if signal == 'buy':
                    break_even_sell_price = price * (1 + maker_fee) / (1 - taker_fee)
                    take_profit_price = break_even_sell_price + (atr * 1.5)
                    stop_loss_price = break_even_sell_price - (atr * 1)
                    if market_price > break_even_sell_price:
                        sol_balance += filled_amount
                        usdc_balance -= filled_amount * price * (1 + maker_fee)
                        asyncio.create_task(place_order('sell', filled_amount, take_profit_price))
                    else:
                        logging.info(f"Skipping sell due to unprofitable trade conditions: Break-even Sell Price: {break_even_sell_price}, Market Price: {market_price}")
                elif signal == 'sell':
                    break_even_buy_price = price * (1 - taker_fee) / (1 + maker_fee)
                    take_profit_price = break_even_buy_price - (atr * 1.5)
                    stop_loss_price = break_even_buy_price + (atr * 1)
                    if market_price < break_even_buy_price:
                        sol_balance -= filled_amount
                        usdc_balance += filled_amount * price * (1 - taker_fee)
                        asyncio.create_task(place_order('buy', filled_amount, take_profit_price))
                    else:
                        logging.info(f"Skipping buy due to unprofitable trade conditions: Break-even Buy Price: {break_even_buy_price}, Market Price: {market_price}")
                trade_log.append({
                    'timestamp': datetime.now(),
                    'side': signal,
                    'amount': filled_amount,
                    'price': price,
                    'status': 'filled',
                    'rsi': indicators['rsi'],
                    'macd_line': indicators['macd_line'],
                    'macd_signal': indicators['macd_signal'],
                    'bb_upper': indicators['bb_upper'],
                    'bb_lower': indicators['bb_lower'],
                    'atr': indicators['atr'],
                    'usdc_balance': usdc_balance,
                    'sol_balance': sol_balance
                })
                logging.info(f"Updated balances - USDC: {usdc_balance}, SOL: {sol_balance}")
            else:
                logging.info(f"Order not filled: {order_status}")
    except Exception as e:
        logging.error(f"Error executing trade: {e}")

# Function to fetch updated balance and ensure only initial balance is used for trading
async def update_balance():
    global usdc_balance, sol_balance
    try:
        synchronize_time()  # Synchronize time before making the API call
        balance = binance.fetch_balance()
        usdc_balance = balance['total']['USDC']
        sol_balance = balance['total']['SOL']
        logging.info(f"Updated USDC balance: {usdc_balance}, SOL balance: {sol_balance}")
    except Exception as e:
        logging.error(f"Error fetching balance: {e}")

# Function to log indicators and market data to a file
def log_data_to_file(indicators, market_price):
    logging.info(f"Market Price: {market_price}")
    logging.info(f"Indicators: {indicators}")

# Main function
async def main():
    synchronize_time()  # Ensure time is synchronized before starting
    await get_initial_balance()
    while True:
        await update_balance()
        prices = get_historical_prices()
        indicators = calculate_indicators(prices)
        ticker = binance.fetch_ticker(symbol)
        market_price = ticker['last']
        log_data_to_file(indicators, market_price)
        
        signal, price, atr = dynamic_signal_generation(indicators, market_price)
        if signal:
            logging.info(f"{signal.capitalize()} signal generated at price: {price}")
            asyncio.create_task(execute_trade(signal, 0, price, atr, indicators))  # Set amount to 0 for initial call

        await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main())

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

# Path to your alert sound file (ensure the file exists at this path)
alert_sound_path = 'D:\Downloads\Loud-Music.mp3'

# Initialize pygame mixer
pygame.mixer.init()

def play_alert_sound():
    pygame.mixer.music.load(alert_sound_path)
    pygame.mixer.music.play()

try:
    # Your main code goes here
    # For demonstration, we'll use a simple example
    while True:
        print("Running...")
        time.sleep(2)  # Simulating some ongoing process
        # Simulate an error after some time
        if time.time() % 10 < 0.1:
            raise Exception("Simulated error")

except Exception as e:
    print(f"An error occurred: {e}")
    play_alert_sound()
    # Keep the program running long enough to hear the sound
    time.sleep(0)  # Adjust the time as needed
