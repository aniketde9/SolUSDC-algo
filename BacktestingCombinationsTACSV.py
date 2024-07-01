import pandas as pd
import ta
import itertools

# Load CSV file
csv_file_path = r'D:\Binance Spot Testnet\SOLUSD2023-2024.csv'
data = pd.read_csv(csv_file_path)

# Ensure the column names are as expected
data.columns = ['snapped_at', 'price', 'market_cap', 'total_volume']

# Convert the 'snapped_at' column to datetime
data['snapped_at'] = pd.to_datetime(data['snapped_at'])

# Convert 'price' column to numeric, forcing errors to NaN and then filling NaNs if any
data['price'] = pd.to_numeric(data['price'], errors='coerce')
data['price'].fillna(method='ffill', inplace=True)  # Forward fill to handle any NaNs

# Calculate technical indicators using ta
data['rsi'] = ta.momentum.RSIIndicator(close=data['price'], window=14).rsi()
macd = ta.trend.MACD(close=data['price'])
data['macd_line'] = macd.macd()
data['macd_signal'] = macd.macd_signal()
bb = ta.volatility.BollingerBands(close=data['price'], window=20, window_dev=2)
data['bb_upper'] = bb.bollinger_hband()
data['bb_lower'] = bb.bollinger_lband()
data['atr'] = ta.volatility.AverageTrueRange(high=data['price'], low=data['price'], close=data['price'], window=14).average_true_range()

# Define parameter ranges
macd_thresholds = [-0.2, -0.1, 0, 0.1, 0.2]
rsi_buy_ranges = [(25, 45), (30, 40), (20, 50)]
rsi_sell_ranges = [(55, 75), (60, 70), (50, 80)]
bb_multipliers_buy = [1.05, 1.07, 1.10]
bb_multipliers_sell = [0.90, 0.93, 0.95]

# Prepare to store results
results = []

# Generate all combinations of parameters
combinations = list(itertools.product(macd_thresholds, rsi_buy_ranges, rsi_sell_ranges, bb_multipliers_buy, bb_multipliers_sell))

# Function to simulate trading
def simulate_trading(data, macd_threshold, rsi_buy_range, rsi_sell_range, bb_multiplier_buy, bb_multiplier_sell):
    initial_balance = 1000  # Starting with 1000 USDC
    usdc_balance = initial_balance
    sol_balance = 0
    maker_fee = 0.00075
    taker_fee = 0.0007125
    minimum_amount = 0.001
    trade_log = []

    for i, row in data.iterrows():
        market_price = row['price']
        rsi = row['rsi']
        macd_line = row['macd_line']
        macd_signal = row['macd_signal']
        bb_upper = row['bb_upper']
        bb_lower = row['bb_lower']
        atr = row['atr']

        # Buy signal
        buy_signal = (macd_line > macd_signal - macd_threshold and rsi_buy_range[0] < rsi < rsi_buy_range[1] and market_price <= bb_lower * bb_multiplier_buy)

        # Sell signal
        sell_signal = (macd_line < macd_signal and rsi_sell_range[0] < rsi < rsi_sell_range[1] and market_price >= bb_upper * bb_multiplier_sell)

        if buy_signal and usdc_balance > minimum_amount * market_price:
            trade_amount = usdc_balance / (market_price * (1 + maker_fee))
            usdc_balance -= trade_amount * market_price * (1 + maker_fee)
            sol_balance += trade_amount
            trade_log.append({'action': 'buy', 'price': market_price, 'amount': trade_amount, 'usdc_balance': usdc_balance, 'sol_balance': sol_balance})
        elif sell_signal and sol_balance > minimum_amount:
            usdc_balance += sol_balance * market_price * (1 - taker_fee)
            trade_log.append({'action': 'sell', 'price': market_price, 'amount': sol_balance, 'usdc_balance': usdc_balance, 'sol_balance': 0})
            sol_balance = 0

    # Evaluate Performance
    final_balance = usdc_balance + (sol_balance * data['price'].iloc[-1])
    profit = final_balance - initial_balance
    return final_balance, profit, trade_log

# Run backtesting for all combinations
for macd_threshold, rsi_buy_range, rsi_sell_range, bb_multiplier_buy, bb_multiplier_sell in combinations:
    final_balance, profit, trade_log = simulate_trading(data, macd_threshold, rsi_buy_range, rsi_sell_range, bb_multiplier_buy, bb_multiplier_sell)
    results.append({
        'macd_threshold': macd_threshold,
        'rsi_buy_range': rsi_buy_range,
        'rsi_sell_range': rsi_sell_range,
        'bb_multiplier_buy': bb_multiplier_buy,
        'bb_multiplier_sell': bb_multiplier_sell,
        'final_balance': final_balance,
        'profit': profit,
        'trade_log': trade_log
    })

# Convert results to DataFrame and sort by profit
results_df = pd.DataFrame(results)
results_df = results_df.sort_values(by='profit', ascending=False)

# Print the best result
best_result = results_df.iloc[0]
print("Best Result:")
print(best_result)

# Save all results to a CSV file
results_df.to_csv('backtesting_results.csv', index=False)

# Display the trade log for the best result
best_trade_log = pd.DataFrame(best_result['trade_log'])
print(best_trade_log)

# Save the trade log for the best result to a CSV file
best_trade_log.to_csv('best_trade_log.csv', index=False)
