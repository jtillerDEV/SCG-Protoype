
# streamlit_app.py
import os, json
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
import streamlit as st
import alpaca_trade_api as tradeapi
import plotly.graph_objects as go
import plotly.express as px
from strategy import compute_smas, latest_signal_reason, load_risk_state, save_risk_state, load_trades

# ----- config -----
SYMBOL = os.getenv("SYMBOL", "AAPL")
FAST = int(os.getenv("FAST", "10"))
SLOW = int(os.getenv("SLOW", "30"))
LOGFILE = "trade_log.csv"
RISK_STATE_FILE = "risk_state.json"
# ------------------

# Removed duplicated functions - now using shared utilities from strategy.py

@st.cache_data(show_spinner=False, ttl=5)
def get_history_df(_api, symbol="AAPL", timeframe="1Min", limit=600):
    bars = _api.get_bars(symbol, timeframe, limit=limit)
    data = [(b.t, b.o, b.h, b.l, b.c, b.v) for b in bars]
    df = pd.DataFrame(data, columns=["time","open","high","low","close","volume"])
    df.set_index("time", inplace=True)
    return df

# Removed duplicated functions - now using shared utilities from strategy.py

# ===== Metrics helpers =====
def load_filled_trades(logfile="trade_log.csv"):
    df = load_trades(logfile)
    if df.empty:
        return df
    # only evaluate filled trades with valid prices
    df = df[df["status"].astype(str).str.lower().eq("filled")]
    df = df[pd.to_numeric(df["filled_avg_price"], errors="coerce").notna()]
    if df.empty:
        return df
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce")
    df["filled_avg_price"] = pd.to_numeric(df["filled_avg_price"], errors="coerce")
    df["side"] = df["side"].str.lower()
    return df

def equity_curve_from_trades_and_prices(trades, prices, init_equity):
    """
    Mark-to-market equity curve at each bar.
    - trades: DataFrame [timestamp, side, qty, filled_avg_price]
    - prices: DataFrame with index 'time' and column 'close'
    - init_equity: float (current account equity is fine)
    """
    if prices.empty:
        return pd.DataFrame()

    prices = prices.copy()
    prices = prices[["close"]].copy()
    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index()

    # running position and cash
    pos = 0.0
    cash = init_equity  # start with equity as cash, build position via trades

    # align trades to price index timestamps (floor to minute)
    t = trades.copy()
    t["timestamp"] = pd.to_datetime(t["timestamp"])
    t["ts_floor"] = t["timestamp"].dt.floor("min")
    t = t.sort_values("ts_floor")

    # create a column to hold position & cash at each bar
    prices["pos"] = 0.0
    prices["cash"] = np.nan

    ti = 0
    trows = t.to_dict("records") if not t.empty else []

    for ts in prices.index:
        # apply all trades whose floored time <= this bar
        while ti < len(trows) and trows[ti]["ts_floor"] <= ts:
            tr = trows[ti]
            q = float(tr["qty"])
            p = float(tr["filled_avg_price"])
            if tr["side"] == "buy":
                cash -= q * p
                pos  += q
            elif tr["side"] == "sell":
                cash += q * p
                pos  -= q
            ti += 1
        prices.at[ts, "pos"] = pos
        prices.at[ts, "cash"] = cash

    prices["cash"] = prices["cash"].ffill().fillna(init_equity)
    prices["equity"] = prices["cash"] + prices["pos"] * prices["close"]
    return prices[["close","pos","cash","equity"]]

def sharpe_ratio(equity, periods_per_year=252*390):  # ~252 trading days * 390 1-min bars
    if len(equity) < 3:
        return None
    ret = equity.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if ret.std() == 0 or ret.empty:
        return None
    mean = ret.mean() * periods_per_year
    vol  = ret.std()  * np.sqrt(periods_per_year)
    return float(mean / vol)

def max_drawdown(equity):
    if len(equity) == 0:
        return None, None
    roll_max = equity.cummax()
    dd = equity / roll_max - 1.0
    return float(dd.min()), dd
# ===== end metrics helpers =====

# --- app ---
st.set_page_config(page_title="SCG Prototype Dashboard", layout="wide")
st.title("SCG Prototype — Transparency & Control")

load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# Initialize API connection
try:
    api = tradeapi.REST(API_KEY, SECRET_KEY, BASE_URL)
    
    # Sidebar controls
    st.sidebar.header("Controls")
    symbol = st.sidebar.text_input("Symbol", value=SYMBOL)
    fast = st.sidebar.number_input("Fast SMA", min_value=2, max_value=200, value=FAST, step=1)
    slow = st.sidebar.number_input("Slow SMA", min_value=3, max_value=400, value=SLOW, step=1)
    if slow <= fast:
        st.sidebar.warning("Slow SMA should be > Fast SMA")
    refresh = st.sidebar.button("Refresh Data")

    # --- Start / Stop (User Pause) ---
    state = load_risk_state(RISK_STATE_FILE)
    colA, colB = st.sidebar.columns(2)
    if colA.button("Start"):
        state["user_paused"] = False
        save_risk_state(state, RISK_STATE_FILE)
    if colB.button("Stop"):
        state["user_paused"] = True
        save_risk_state(state, RISK_STATE_FILE)

    user_paused = state.get("user_paused", False)
    st.sidebar.caption(f"Trading is **{'PAUSED' if user_paused else 'RUNNING'}**")

    # Account snapshot
    acct = api.get_account()
    equity = float(acct.equity)
    cash = float(acct.cash)
    # maintain peak equity
    peak = state.get("peak_equity")
    if peak is None or equity > peak:
        peak = equity
    state["peak_equity"] = peak
    state["last_equity"] = equity
    save_risk_state(state, RISK_STATE_FILE)
    dd_pct = 0.0 if peak == 0 else max(0.0, (peak - equity) / peak)
    auto_paused = state.get("auto_paused", False)
    paused_banner = auto_paused or user_paused

    # Metrics row
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Equity", f"${equity:,.2f}")
    m2.metric("Peak Equity", f"${peak:,.2f}")
    m3.metric("Drawdown", f"{dd_pct*100:.2f}%")
    m4.metric("Status", "PAUSED" if paused_banner else "RUNNING")

    if paused_banner:
        st.warning("PAUSED — trading disabled (User Pause or Auto-Pause).")

    # Position info
    pos_qty = 0
    try:
        pos = api.get_position(symbol)
        pos_qty = float(pos.qty)
    except Exception:
        pos_qty = 0.0

    # Price history + SMAs
    if refresh:
        st.cache_data.clear()
    df = get_history_df(api, symbol=symbol, timeframe="1Min", limit=max(600, slow+50))
    df = compute_smas(df, fast=fast, slow=slow)
    signal, reason, conf = latest_signal_reason(df, fast=fast, slow=slow)

    # ===== Performance metrics section =====
    st.subheader("Performance Metrics")

    filled = load_filled_trades(LOGFILE)
    if filled.empty:
        st.info("No filled trades yet → PnL/Sharpe/Drawdown will appear after your first fill.")
    else:
        # build equity curve marked to market on each bar
        prices_for_curve = df[["close"]].copy()
        eq_df = equity_curve_from_trades_and_prices(filled, prices_for_curve, init_equity=equity)

        if eq_df.empty or eq_df["equity"].isna().all():
            st.warning("Not enough price data to compute equity curve.")
        else:
            # PnL since first point
            pnl_abs = eq_df["equity"].iloc[-1] - eq_df["equity"].iloc[0]
            pnl_pct = pnl_abs / eq_df["equity"].iloc[0] if eq_df["equity"].iloc[0] else 0.0
            sr = sharpe_ratio(eq_df["equity"])
            mdd, dd_series = max_drawdown(eq_df["equity"])

            c1, c2, c3 = st.columns(3)
            c1.metric("PnL (since start)", f"${pnl_abs:,.2f}", f"{pnl_pct*100:.2f}%")
            c2.metric("Sharpe (approx)", "—" if sr is None else f"{sr:.2f}")
            c3.metric("Max Drawdown", "—" if mdd is None else f"{mdd*100:.2f}%")

            # Enhanced equity curve chart
            
            # Create equity curve with Plotly
            fig_equity = go.Figure()
            fig_equity.add_trace(go.Scatter(
                x=eq_df.index,
                y=eq_df["equity"],
                mode='lines',
                name='Equity (M2M)',
                line=dict(color='#1f77b4', width=3),
                fill='tonexty'
            ))
            fig_equity.update_layout(
                title="Equity Curve (Mark-to-Market)",
                xaxis_title="Time",
                yaxis_title="Equity ($)",
                height=400,
                showlegend=True,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(size=12)
            )
            st.plotly_chart(fig_equity, width='stretch')
            
            # Enhanced drawdown chart
            if dd_series is not None:
                fig_dd = go.Figure()
                fig_dd.add_trace(go.Scatter(
                    x=dd_series.index,
                    y=dd_series.values,
                    mode='lines',
                    name='Drawdown',
                    line=dict(color='#ff7f0e', width=2),
                    fill='tozeroy'
                ))
                fig_dd.update_layout(
                    title="Drawdown Over Time",
                    xaxis_title="Time",
                    yaxis_title="Drawdown (%)",
                    height=300,
                    showlegend=True,
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    font=dict(size=12)
                )
                st.plotly_chart(fig_dd, width='stretch')

    left, right = st.columns([2,1])

    with left:
        st.subheader(f"Price & SMAs — {symbol}")
        plot_df = df[["close", f"SMA{fast}", f"SMA{slow}"]].dropna().tail(600)
        
        # Enhanced price chart with Plotly
        fig_price = go.Figure()
        
        # Add price line
        fig_price.add_trace(go.Scatter(
            x=plot_df.index,
            y=plot_df["close"],
            mode='lines',
            name='Close Price',
            line=dict(color='#d62728', width=2)
        ))
        
        # Add SMA lines
        fig_price.add_trace(go.Scatter(
            x=plot_df.index,
            y=plot_df[f"SMA{fast}"],
            mode='lines',
            name=f'SMA({fast})',
            line=dict(color='#1f77b4', width=2, dash='dash')
        ))
        
        fig_price.add_trace(go.Scatter(
            x=plot_df.index,
            y=plot_df[f"SMA{slow}"],
            mode='lines',
            name=f'SMA({slow})',
            line=dict(color='#ff7f0e', width=2, dash='dot')
        ))
        
        fig_price.update_layout(
            title=f"{symbol} Price & Moving Averages",
            xaxis_title="Time",
            yaxis_title="Price ($)",
            height=500,
            showlegend=True,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(size=12),
            hovermode='x unified'
        )
        
        st.plotly_chart(fig_price, width='stretch')

    with right:
        st.subheader("Latest Signal")
        
        # Colored signal badges
        sig_txt = signal.upper()
        if signal == "buy":
            st.success(f"Signal: {sig_txt}")
        elif signal == "sell":
            st.error(f"Signal: {sig_txt}")
        else:
            st.info(f"Signal: {sig_txt}")
            
        st.write(f"**Reason:** {reason}")
        st.write(f"**Confidence:** {conf:.4f}")
        st.write(f"**Current Position:** {pos_qty:.0f}")

        if st.button("Clear Auto-Pause"):
            state = load_risk_state(RISK_STATE_FILE)
            state["auto_paused"] = False
            save_risk_state(state, RISK_STATE_FILE)
            st.success("Auto-pause cleared. (Refresh to update)")

    # Enhanced Trade log table
    st.subheader("Trade Log")
    trades = load_trades()
    if not trades.empty:
        # Prepare data for display
        display_trades = trades.copy()
        display_trades = display_trades.sort_values("timestamp", ascending=False)
        
        # Format the data for better display
        display_trades["timestamp"] = pd.to_datetime(display_trades["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S")
        display_trades["filled_avg_price"] = display_trades["filled_avg_price"].round(2)
        display_trades["confidence"] = display_trades["confidence"].round(6)
        
        # Add color coding for buy/sell
        def color_side(val):
            if val == 'buy':
                return 'background-color: #d4edda; color: #155724'
            elif val == 'sell':
                return 'background-color: #f8d7da; color: #721c24'
            return ''
        
        # Select and rename columns for display
        cols = ["timestamp","symbol","side","qty","status","filled_avg_price","reason","confidence"]
        display_cols = ["Timestamp","Symbol","Side","Quantity","Status","Price","Reason","Confidence"]
        
        styled_trades = display_trades[cols].copy()
        styled_trades.columns = display_cols
        
        # Apply styling
        styled_df = styled_trades.style.applymap(color_side, subset=['Side'])
        
        st.dataframe(
            styled_df,
            width='stretch',
            height=400
        )
        
        # Add summary stats
        total_trades = len(trades)
        buy_trades = len(trades[trades['side'] == 'buy'])
        sell_trades = len(trades[trades['side'] == 'sell'])
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Trades", total_trades)
        col2.metric("Buy Orders", buy_trades)
        col3.metric("Sell Orders", sell_trades)
        
    else:
        st.info("No trades logged yet. Once a live order fills, it will appear here.")

    # Show data freshness
    latest_time = df.index[-1] if not df.empty else "No data"
    st.caption(f"Chart Data: {latest_time} | Dashboard Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

except Exception as e:
    st.error(f"Connection Error: {str(e)}")
    st.info("This is likely due to SSL certificate issues on your corporate network. The dashboard will work properly when you test it from home.")
    
    # Show demo data when API is not available
    st.subheader("Demo Mode (API Unavailable)")
    
    # Demo metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Equity", "$10,000.00")
    m2.metric("Peak Equity", "$10,500.00")
    m3.metric("Drawdown", "4.76%")
    m4.metric("Status", "RUNNING")
    
    # Demo signal
    st.subheader("Demo Signal")
    st.write("**Signal:** HOLD")
    st.write("**Reason:** SMA(10) is above SMA(30); no crossover")
    st.write("**Confidence:** 0.0234")
    st.write("**Current Position:** 0")
    
    st.info("This is demo data. Real data will appear when API connection is available.")
