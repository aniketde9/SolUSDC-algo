import re
import pandas as pd

# Corrected file path
log_file_path = r'D:\Binance Spot Testnet\Log.txt'

# Read the log file
with open(log_file_path, 'r') as file:
    log_lines = file.readlines()

# Initialize lists to store data
timestamps = []
market_prices = []
indicators_list = []

# Regex patterns to match log lines
price_pattern = re.compile(r"Market Price: (\d+\.\d+)")
indicator_pattern = re.compile(
    r"Indicators: \{'timestamp': datetime\.datetime\(\d+, \d+, \d+, \d+, \d+, \d+, \d+\), 'rsi': np\.float64\(([\d\.]+)\), 'macd_line': np\.float64\(([-\d\.]+)\), 'macd_signal': np\.float64\(([-\d\.]+)\), 'bb_upper': np\.float64\(([\d\.]+)\), 'bb_lower': np\.float64\(([\d\.]+)\), 'atr': np\.float64\(([\d\.]+)\)\}")

# Parse the log lines
for line in log_lines:
    price_match = price_pattern.search(line)
    indicator_match = indicator_pattern.search(line)
    if price_match:
        market_prices.append(float(price_match.group(1)))
    if indicator_match:
        rsi = float(indicator_match.group(1))
        macd_line = float(indicator_match.group(2))
        macd_signal = float(indicator_match.group(3))
        bb_upper = float(indicator_match.group(4))
        bb_lower = float(indicator_match.group(5))
        atr = float(indicator_match.group(6))
        indicators_list.append({
            'rsi': rsi,
            'macd_line': macd_line,
            'macd_signal': macd_signal,
            'bb_upper': bb_upper,
            'bb_lower': bb_lower,
            'atr': atr
        })

# Ensure both lists have the same length
min_length = min(len(market_prices), len(indicators_list))
market_prices = market_prices[:min_length]
indicators_list = indicators_list[:min_length]

# Create a DataFrame
data = pd.DataFrame(indicators_list)
data['market_price'] = market_prices

# Step 2: Simulate Trading
initial_balance = 1000  # Starting with 1000 USDC
usdc_balance = initial_balance
sol_balance = 0
maker_fee = 0.00075
taker_fee = 0.0007125
minimum_amount = 0.001
trade_log = []

for i, row in data.iterrows():
    market_price = row['market_price']
    rsi = row['rsi']
    macd_line = row['macd_line']
    macd_signal = row['macd_signal']
    bb_upper = row['bb_upper']
    bb_lower = row['bb_lower']
    atr = row['atr']

    # Buy signal
    buy_signal = (macd_line > macd_signal and 25 < rsi < 45 and market_price <= bb_lower * 1.1)

    # Sell signal with updated logic
    sell_signal = (macd_line < macd_signal and 75 > rsi > 55 and market_price >= bb_upper * 0.90)

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
final_balance = usdc_balance + (sol_balance * market_prices[-1])
profit = final_balance - initial_balance

print(f"Initial Balance: {initial_balance} USDC")
print(f"Final Balance: {final_balance} USDC")
print(f"Profit: {profit} USDC")

# Display the trade log
trade_log_df = pd.DataFrame(trade_log)
print(trade_log_df)

# Save the trade log to a CSV file
trade_log_df.to_csv('trade_log.csv', index=False)
