# strategy.py
import pandas as pd
import os
import json
import csv
from datetime import datetime

def df_from_bars(bars):
    data = [(b.t, b.o, b.h, b.l, b.c, b.v) for b in bars]
    df = pd.DataFrame(data, columns=["time","open","high","low","close","volume"])
    df.set_index("time", inplace=True)
    return df

def get_history_df(api, symbol="AAPL", timeframe="1Min", limit=300):
    bars = api.get_bars(symbol, timeframe, limit=limit)
    return df_from_bars(bars)

def compute_smas(df, fast=10, slow=30):
    """Compute Simple Moving Averages and return updated dataframe"""
    df = df.copy()
    df[f"SMA{fast}"] = df["close"].rolling(fast).mean()
    df[f"SMA{slow}"] = df["close"].rolling(slow).mean()
    return df

def latest_signal_reason(df, fast=10, slow=30):
    """Get latest signal, reason, and confidence - compatible with streamlit_app.py"""
    fcol, scol = f"SMA{fast}", f"SMA{slow}"
    if df[scol].isna().iloc[-1]:
        return "none", "Not enough data", 0.0
    prev_fast, prev_slow = df[fcol].iloc[-2], df[scol].iloc[-2]
    curr_fast, curr_slow = df[fcol].iloc[-1], df[scol].iloc[-1]
    eps = 1e-9
    confidence = abs(curr_fast - curr_slow) / max(abs(curr_slow), eps)
    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "buy", f"BUY — SMA({fast}) crossed above SMA({slow})", confidence
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return "sell", f"SELL — SMA({fast}) crossed below SMA({slow})", confidence
    regime = "above" if curr_fast > curr_slow else "below" if curr_fast < curr_slow else "equal"
    return "none", f"HOLD — SMA({fast}) is {regime} SMA({slow}); no crossover", confidence

# Risk Management Utilities
def load_risk_state(risk_state_file="risk_state.json"):
    """Load risk state from JSON file"""
    if os.path.exists(risk_state_file):
        try:
            with open(risk_state_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"peak_equity": None, "auto_paused": False, "last_equity": None, "user_paused": False}

def save_risk_state(state, risk_state_file="risk_state.json"):
    """Save risk state to JSON file"""
    with open(risk_state_file, "w") as f:
        json.dump(state, f)

# Trade Logging Utilities
def log_trade(trade_data, logfile="trade_log.csv"):
    """Log a trade to CSV file"""
    header = ["timestamp","symbol","qty","side","status","filled_avg_price","reason","confidence"]
    write_header = not os.path.exists(logfile)
    with open(logfile, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        if write_header: w.writeheader()
        w.writerow(trade_data)

def load_trades(logfile="trade_log.csv"):
    """Load trades from CSV file with proper error handling"""
    if not os.path.exists(logfile):
        return pd.DataFrame(columns=["timestamp","symbol","qty","side","status","filled_avg_price","reason","confidence"])
    
    try:
        df = pd.read_csv(logfile)
        
        # Ensure all required columns exist
        required_cols = ["timestamp","symbol","qty","side","status","filled_avg_price","reason","confidence"]
        for col in required_cols:
            if col not in df.columns:
                df[col] = "" if col in ["reason"] else 0.0 if col in ["confidence"] else ""
        
        # Convert types
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        if "filled_avg_price" in df.columns:
            df["filled_avg_price"] = pd.to_numeric(df["filled_avg_price"], errors="coerce")
        if "confidence" in df.columns:
            df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")
        return df
    except Exception as e:
        print(f"Error loading trade log: {e}")
        return pd.DataFrame(columns=["timestamp","symbol","qty","side","status","filled_avg_price","reason","confidence"])

def sma_cross_signal(df, fast=10, slow=30):
    df = df.copy()
    df[f"sma_{fast}"] = df["close"].rolling(fast).mean()
    df[f"sma_{slow}"] = df["close"].rolling(slow).mean()
    if df[f"sma_{slow}"].isna().iloc[-1]:  # not enough data yet
        return None
    
    prev_fast = df[f"sma_{fast}"].iloc[-2]
    prev_slow = df[f"sma_{slow}"].iloc[-2]
    curr_fast = df[f"sma_{fast}"].iloc[-1]
    curr_slow = df[f"sma_{slow}"].iloc[-1]
    
    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "buy"
    elif prev_fast >= prev_slow and curr_fast < curr_slow:
        return "sell"
    else:
        return "hold"
    

def describe_sma_signal(df, fast=10, slow=30):
    """
    Returns (reason_str, confidence_float) for the latest bar.
    Confidence ~ absolute distance between SMAs as a % of slow SMA.
    """
    fcol, scol = f"sma_{fast}", f"sma_{slow}"
    if df[scol].isna().iloc[-1]:
        return ("Not enough data", 0.0)
    prev_fast, prev_slow = df[fcol].iloc[-2], df[scol].iloc[-2]
    curr_fast, curr_slow = df[fcol].iloc[-1], df[scol].iloc[-1]

    # confidence = normalized SMA separation
    eps = 1e-9
    confidence = abs(curr_fast - curr_slow) / max(abs(curr_slow), eps)

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return (f"BUY — SMA({fast}) crossed above SMA({slow})", confidence)
    if prev_fast >= prev_slow and curr_fast < curr_slow:
        return (f"SELL — SMA({fast}) crossed below SMA({slow})", confidence)
    # no cross; describe regime
    regime = "above" if curr_fast > curr_slow else "below" if curr_fast < curr_slow else "equal"
    return (f"HOLD — SMA({fast}) is {regime} SMA({slow}); no crossover", confidence)
