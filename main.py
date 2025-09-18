from pickle import FALSE
import os, csv, time, json
from datetime import datetime
from dotenv import load_dotenv
import alpaca_trade_api as tradeapi
from strategy import get_history_df, sma_cross_signal, describe_sma_signal, load_risk_state, save_risk_state, log_trade

# Automated SMA Crossover Trading Bot
# Implements a simple moving average crossover strategy with risk management

# Load environment variables and validate API credentials
load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
BASE_URL = os.getenv("ALPACA_BASE_URL")
if not all([API_KEY, SECRET_KEY, BASE_URL]):
    raise SystemExit("Missing ALPACA_* env vars. Check your .env file.")

# ---- Trading Configuration ----
SYMBOL   = "AAPL"        # Stock symbol to trade
QTY      = 1000          # Number of shares per trade
FAST     = 10            # Fast SMA period (shorter-term trend)
SLOW     = 20            # Slow SMA period (longer-term trend)
DRY_RUN  = False         # Set to True to test without placing real orders
INTERVAL_SEC = 15        # Seconds between strategy checks
LOGFILE  = "trade_log.csv"        # File to log all trades
RISK_STATE_FILE = "risk_state.json"  # File to persist risk management state
MAX_DD_PCT = 0.05        # Maximum drawdown percentage before auto-pause (5%)
# ---------------------------------


def update_drawdown_and_guardrail(acct_equity):
    """
    Risk management function that tracks peak equity and enforces drawdown limits.
    
    Args:
        acct_equity: Current account equity value
        
    Returns:
        tuple: (auto_paused: bool, dd_pct: float, peak: float)
    """
    state = load_risk_state(RISK_STATE_FILE)
    eq = float(acct_equity)
    peak = state["peak_equity"]

    # Update peak equity if current equity is higher
    if peak is None or eq > peak:
        peak = eq

    # Calculate current drawdown percentage
    dd_pct = 0.0 if peak == 0 else max(0.0, (peak - eq) / peak)
    auto_paused = state.get("auto_paused", False)

    # Trigger auto-pause if drawdown exceeds maximum allowed
    if dd_pct >= MAX_DD_PCT:
        auto_paused = True  # trip the breaker

    state.update({"peak_equity": peak, "last_equity": eq, "auto_paused": auto_paused})
    save_risk_state(state, RISK_STATE_FILE)
    return auto_paused, dd_pct, peak

def clear_auto_pause():
    """Manually clear the auto-pause flag to resume trading after drawdown recovery."""
    state = load_risk_state(RISK_STATE_FILE)
    state["auto_paused"] = False
    save_risk_state(state, RISK_STATE_FILE)

def is_user_paused():
    """Check if user has manually paused trading."""
    state = load_risk_state(RISK_STATE_FILE)
    return bool(state.get("user_paused", False))

def position_qty(api, symbol):
    """Get current position quantity for a symbol. Returns 0 if no position or error."""
    try:
        pos = api.get_position(symbol)
        return int(float(pos.qty))
    except Exception:
        return 0

def place_and_log(api, side, qty, reason="", confidence=0.0):
    """Place a market order and log the trade details to file."""
    order = api.submit_order(symbol=SYMBOL, qty=qty, side=side, type="market", time_in_force="day")
    time.sleep(1.0)  # Brief wait for order to fill
    order = api.get_order(order.id)
    filled = getattr(order, "filled_avg_price", "")
    
    # Log trade details for analysis
    log_trade({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "symbol": order.symbol,
        "qty": order.qty,
        "side": order.side,
        "status": order.status,
        "filled_avg_price": filled,
        "reason": reason,
        "confidence": round(confidence, 6),
    }, LOGFILE)
    print(f"{side.upper()} logged → {filled}")

def backtest_strategy(api):
    """
    Run backtest on historical data to validate SMA crossover strategy.
    
    This function simulates the trading strategy on historical data to:
    - Validate signal generation logic
    - Show potential performance
    - Debug strategy parameters
    """
    print(f"Running backtest on {SYMBOL} with SMA({FAST}/{SLOW})...")
    
    # Get historical price data
    df = get_history_df(api, SYMBOL, timeframe="1Min", limit=1000)
    print(f"Got {len(df)} historical bars")
    
    # Calculate moving averages
    df[f"sma_{FAST}"] = df["close"].rolling(FAST).mean()
    df[f"sma_{SLOW}"] = df["close"].rolling(SLOW).mean()
    
    print(f"\nRecent SMA values:")
    print("-" * 60)
    recent_data = df.tail(10)
    for i, (timestamp, row) in enumerate(recent_data.iterrows()):
        sma_fast = row[f"sma_{FAST}"]
        sma_slow = row[f"sma_{SLOW}"]
        close = row["close"]
        print(f"{timestamp} | Close: ${close:8.2f} | SMA({FAST}): {sma_fast:8.2f} | SMA({SLOW}): {sma_slow:8.2f}")
    
    valid_sma_data = df[f"sma_{SLOW}"].dropna()
    print(f"\nValid SMA data points: {len(valid_sma_data)} out of {len(df)}")
    
    # Simulate trading signals based on SMA crossovers
    signals = []
    position = 0  # 0 = no position, 1 = long, -1 = short
    
    for i in range(SLOW, len(df)):
        if df[f"sma_{SLOW}"].iloc[i] is None:
            continue
            
        # Get previous and current SMA values for crossover detection
        prev_fast = df[f"sma_{FAST}"].iloc[i-1]
        prev_slow = df[f"sma_{SLOW}"].iloc[i-1]
        curr_fast = df[f"sma_{FAST}"].iloc[i]
        curr_slow = df[f"sma_{SLOW}"].iloc[i]
        
        timestamp = df.index[i]
        price = df["close"].iloc[i]
        
        # Detect bullish crossover: fast SMA crosses above slow SMA
        if prev_fast <= prev_slow and curr_fast > curr_slow and position <= 0:
            signals.append({
                "timestamp": timestamp,
                "signal": "BUY",
                "price": price,
                "sma_fast": curr_fast,
                "sma_slow": curr_slow
            })
            position = 1
            
        # Detect bearish crossover: fast SMA crosses below slow SMA
        elif prev_fast >= prev_slow and curr_fast < curr_slow and position >= 0:
            signals.append({
                "timestamp": timestamp,
                "signal": "SELL", 
                "price": price,
                "sma_fast": curr_fast,
                "sma_slow": curr_slow
            })
            position = -1
    
    print(f"\nFound {len(signals)} signals:")
    print("-" * 80)
    for signal in signals[-10:]:  # Show last 10 signals
        print(f"{signal['timestamp']} | {signal['signal']:4} | ${signal['price']:8.2f} | SMA({FAST}): {signal['sma_fast']:8.2f} | SMA({SLOW}): {signal['sma_slow']:8.2f}")
    
    if len(signals) >= 2:
        print(f"\nLatest signal: {signals[-1]['signal']} at ${signals[-1]['price']:.2f}")
        print(f"Current price: ${df['close'].iloc[-1]:.2f}")
        print(f"Current SMA({FAST}): {df[f'sma_{FAST}'].iloc[-1]:.2f}")
        print(f"Current SMA({SLOW}): {df[f'sma_{SLOW}'].iloc[-1]:.2f}")

def loop(api):
    """
    Main trading loop that continuously monitors for signals and executes trades.
    
    The loop:
    1. Checks account status and risk management
    2. Calculates SMA signals
    3. Determines if a trade should be placed
    4. Executes trades (if not in DRY_RUN mode)
    5. Waits for the next cycle
    """
    print(f"Connected. Starting automated trading loop (every {INTERVAL_SEC} seconds).")
    print("Press Ctrl+C to stop.")
    
    while True:
        try:
            # Check account status and update risk management
            acct = api.get_account()
            auto_paused, dd_pct, peak = update_drawdown_and_guardrail(acct.equity)
            print(f"Account: {acct.status} | Cash: {acct.cash}")
            print(f"Equity: {acct.equity} | Cash: {acct.cash}")
            print(f"Peak: {peak:.2f} | DD: {dd_pct*100:.2f}% | AutoPaused: {auto_paused}")

            # Get historical data and calculate signals
            df = get_history_df(api, SYMBOL, timeframe="1Min", limit=max(300, SLOW+50))
            
            # Calculate moving averages for signal generation
            df[f"sma_{FAST}"] = df["close"].rolling(FAST).mean()
            df[f"sma_{SLOW}"] = df["close"].rolling(SLOW).mean()
            
            # Generate trading signal based on SMA crossover
            signal = sma_cross_signal(df, fast=FAST, slow=SLOW)
            print(f"SMA({FAST}/{SLOW}) signal: {signal}")

            # Get detailed explanation of the signal
            reason, confidence = describe_sma_signal(df, fast=FAST, slow=SLOW)
            print(f"Reason: {reason} | Confidence: {confidence:.4f}")

            # Check for manual pause or risk management blocks
            if is_user_paused():
                print("User pause is ON — skipping trading this cycle.")
                continue

            if auto_paused:
                print("Guardrail: Trading blocked due to drawdown. Use 'r' command or clear_auto_pause() to resume.")
                continue

            # Determine current position and trading decision
            qty_now = position_qty(api, SYMBOL)
            should_buy  = signal == "buy"  and qty_now <= 0  # Only buy if no current long position
            should_sell = signal == "sell" and qty_now > 0   # Only sell if we have a position

            if signal is None:
                print("No signal yet.")
                continue

            # Execute trade decision
            action = "BUY" if should_buy else "SELL" if should_sell else "HOLD"
            if DRY_RUN or action == "HOLD":
                print(f"DRY_RUN={DRY_RUN} → {action} {SYMBOL} (pos={qty_now})")
                continue

            # Place actual trades
            if should_buy:
                place_and_log(api, "buy", QTY, reason, confidence)
            elif should_sell:
                place_and_log(api, "sell", qty_now, reason, confidence)

        except tradeapi.rest.APIError as e:
            # Handle API rate limits or errors
            print(f"APIError: {e}. Backing off 3s...")
            time.sleep(3)
        except KeyboardInterrupt:
            # Graceful shutdown on Ctrl+C
            print("Interrupted. Exiting."); break
        except Exception as e:
            # Handle unexpected errors
            print(f"Unexpected error: {e}")
            time.sleep(1)
        
        print(f"Waiting {INTERVAL_SEC} seconds until next cycle...")
        time.sleep(INTERVAL_SEC)

def main():
    """
    Main entry point for the trading bot.
    
    Usage:
        python main.py          # Run live trading
        python main.py backtest # Run backtest on historical data
    """
    import sys
    
    # Initialize Alpaca API connection
    api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL)

    # Check if backtest mode was requested
    if len(sys.argv) > 1 and sys.argv[1] == "backtest":
        backtest_strategy(api)
        return

    # Verify account connection and data access
    acct = api.get_account()
    print(f"Status: {acct.status} | Cash: {acct.cash}")
    
    # Test market data access
    try:
        bars = api.get_bars(SYMBOL, "1Min", limit=5)
        print(f"Successfully got {len(bars)} bars for {SYMBOL}")
        for b in bars:
            print(f"{b.t} | O:{b.o} C:{b.c}")
    except Exception as e:
        print(f"Error getting bars for {SYMBOL}: {e}")
        return

    # Start the main trading loop
    loop(api)

if __name__ == "__main__":
    main()
