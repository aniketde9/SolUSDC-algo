import pandas as pd
import ta
import re

# Load CSV file
csv_file_path = r'D:\Binance Spot Testnet\SOLUSD2023-2024.csv'
data = pd.read_csv(csv_file_path)

# Ensure the column names are as expected
data.columns = ['snapped_at', 'price', 'market_cap', 'total_volume']

# Convert the 'snapped_at' column to datetime
data['snapped_at'] = pd.to_datetime(data['snapped_at'])

# Calculate technical indicators using ta
data['rsi'] = ta.momentum.RSIIndicator(close=data['price'], window=14).rsi()
macd = ta.trend.MACD(close=data['price'])
data['macd_line'] = macd.macd()
data['macd_signal'] = macd.macd_signal()
bb = ta.volatility.BollingerBands(close=data['price'], window=20, window_dev=2)
data['bb_upper'] = bb.bollinger_hband()
data['bb_lower'] = bb.bollinger_lband()
data['atr'] = ta.volatility.AverageTrueRange(high=data['price'], low=data['price'], close=data['price'], window=14).average_true_range()

# Check for NaN values and drop them
data.dropna(inplace=True)

# Step 2: Simulate Trading
initial_balance = 1000  # Starting with 1000 USDC
usdc_balance = initial_balance
sol_balance = 0
maker_fee = 0.00075
taker_fee = 0.0007125
minimum_amount = 0.001
trade_log = []

# Iterate over the rows of the DataFrame
for i, row in data.iterrows():
    market_price = row['price']
    rsi = row['rsi']
    macd_line = row['macd_line']
    macd_signal = row['macd_signal']
    bb_upper = row['bb_upper']
    bb_lower = row['bb_lower']
    atr = row['atr']

    # Print the indicators for debugging
    print(f"Row {i}: Market Price: {market_price}, RSI: {rsi}, MACD Line: {macd_line}, MACD Signal: {macd_signal}, BB Upper: {bb_upper}, BB Lower: {bb_lower}")

    # Buy signal
    buy_signal = (macd_line > macd_signal and 25 < rsi < 45 and market_price <= bb_lower * 1.5)
    print(f"Buy Signal: {buy_signal}")

    # Sell signal with updated logic
    sell_signal = (macd_line < macd_signal and 75 > rsi > 55 and market_price >= bb_upper * 0.50)
    print(f"Sell Signal: {sell_signal}")

    if buy_signal and usdc_balance > minimum_amount * market_price:
        trade_amount = usdc_balance / (market_price * (1 + maker_fee))
        usdc_balance -= trade_amount * market_price * (1 + maker_fee)
        sol_balance += trade_amount
        trade_log.append({'action': 'buy', 'price': market_price, 'amount': trade_amount, 'usdc_balance': usdc_balance, 'sol_balance': sol_balance})
    elif sell_signal and sol_balance > minimum_amount:
        usdc_balance += sol_balance * market_price * (1 - taker_fee)
        trade_log.append({'action': 'sell', 'price': market_price, 'amount': sol_balance, 'usdc_balance': usdc_balance, 'sol_balance': 0})
        sol_balance = 0

# Step 3: Evaluate Performance
final_balance = usdc_balance + (sol_balance * data['price'].iloc[-1])
profit = final_balance - initial_balance

print(f"Initial Balance: {initial_balance} USDC")
print(f"Final Balance: {final_balance} USDC")
print(f"Profit: {profit} USDC")

# Display the trade log
trade_log_df = pd.DataFrame(trade_log)
print(trade_log_df)

# Save the trade log to a CSV file
trade_log_df.to_csv('trade_log.csv', index=False)
