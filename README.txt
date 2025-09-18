# SCG Prototype Trading System

> A small, auditable, rules-based trading prototype that demonstrates **secure broker/API integration, automation, transparency, control,** and **risk management**.  
> **Tech:** Python, Alpaca (paper), Streamlit, Pandas, NumPy.

---

## ⚠️ Important Notices

- **Not investment advice.** This software is provided **for educational and demonstration purposes only**. It does **not** provide financial advice, portfolio management, or brokerage services.
- **Paper trading by default.** The sample configuration points to **Alpaca Paper**. Do not connect to a live brokerage unless you fully understand the code and risks.
- **No warranty.** The software is provided **“as is”**, without warranty of any kind. Use at your own risk.
- **Hypothetical performance.** Backtest results and paper trading fills are **hypothetical** and may not reflect real market conditions, liquidity, slippage, fees, or latency.
- **Regulatory & compliance.** You are responsible for complying with all laws/regulations in your jurisdiction (e.g., FCA/SEC/CFD disclosures, auto-trading rules, audit/trail requirements).
- **Keys & data handling.** Never commit API keys. Use environment variables and secret management. Logs may contain sensitive operational info—handle accordingly.

---

## Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Running](#running)
- [Dashboard](#dashboard)
- [Risk Management](#risk-management)
- [Explainability & Audit Trail](#explainability--audit-trail)
- [Metrics](#metrics)
- [Security Practices](#security-practices)
- [Operational Notes](#operational-notes)
- [Troubleshooting](#troubleshooting)
- [Testing](#testing)
- [Roadmap](#roadmap)
- [License](#license)

---

## Overview

Implements a **Simple Moving Average (SMA) crossover** strategy with:
- a headless bot (`main.py`) for automated trading,
- a **Streamlit dashboard** (`streamlit_app.py`) for **live transparency & control**,
- centralized strategy utilities (`strategy.py`),
- risk state persistence and trade logging for **auditability**.

Designed to mirror enterprise themes: **automation, transparency, control, security,** and **risk discipline**.

---

## Key Features

- **Secure Broker Integration:** Alpaca Paper API; keys via `.env`.
- **Rules-Based Strategy:** SMA(fast/slow) crossover with dry-run/live modes.
- **Manual Override:** Start/Stop (user pause) from the dashboard; bot respects it.
- **Risk Guardrail:** **Auto-pause on max drawdown** vs peak equity (default 5%).
- **Explainability:** Each trade logs a **reason** and **confidence score**.
- **Audit Trail:** CSV logging of timestamp, symbol, side, qty, fill, reason, confidence.
- **Backtest Mode:** Inspect signals on historical bars before going live.
- **Dashboard:** Equity/peak/DD, price+SMAs chart, latest signal, trade log, metrics (PnL, Sharpe, MaxDD).

---

## System Architecture

```
/scg-prototype
├── main.py             # Trading loop (reads state, places orders, logs)
├── streamlit_app.py    # Dashboard (control + visibility)
├── strategy.py         # SMA logic, data helpers, explainability
├── backtest.py         # (optional) backtest helpers
├── trade_log.csv       # Audit log (created at runtime)
├── risk_state.json     # Peak equity, auto/user pause flags (runtime)
├── .env                # API keys (never commit)
├── requirements.txt    # pinned deps (recommended)
└── README.md
```

---

## Requirements

- Python 3.10+  
- An **Alpaca** account (Paper trading)  
- OS: Windows/macOS/Linux

---

## Quick Start

```bash
# clone & enter
git clone <your-repo-url>
cd scg-prototype

# venv
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

# deps
pip install --upgrade pip
pip install -r requirements.txt   # or: pip install alpaca-trade-api streamlit pandas numpy python-dotenv
```

Create `.env` in project root:

```env
ALPACA_API_KEY=YOUR_KEY
ALPACA_SECRET_KEY=YOUR_SECRET
ALPACA_BASE_URL=https://paper-api.alpaca.markets
# Optional defaults used by dashboard:
SYMBOL=AAPL
FAST=10
SLOW=30
```

> **Security tip:** After any public sharing, **regenerate your Alpaca secret** and confirm `.env` is in `.gitignore`.

---

## Configuration

```python
SYMBOL = "AAPL"      # test with equities; crypto symbols like "BTC/USD" if you want 24/7 fills
FAST   = 10
SLOW   = 30
QTY    = 1           # position size per trade (shares/units)
DRY_RUN = True       # safe mode; set False to actually submit orders (paper)
MAX_DD_PCT = 0.05    # 5% drawdown auto-pause
```

---

## Running

**Bot (terminal):**
```bash
python main.py
```

**Dashboard (browser):**
```bash
streamlit run streamlit_app.py
# Opens http://localhost:8501
```

---

## Dashboard

- **Top metrics:** Equity, Peak Equity, Drawdown %, Status (RUNNING/PAUSED)
- **Price & SMAs chart:** `close`, `SMA(fast)`, `SMA(slow)`
- **Latest signal:** **reason** + **confidence** + current position
- **Controls:** Start/Stop, SMA parameters, symbol, refresh
- **Trade Log:** Most recent trades with fill, reason, confidence
- **Performance:** PnL, **Sharpe (approx)**, **Max Drawdown**, equity & drawdown charts

---

## Risk Management

- **Peak Equity Tracking:** Stored in `risk_state.json`.
- **Auto-Pause on Drawdown:** Trading halts if drawdown ≥ threshold.
- **Manual Override:** “Stop” sets `user_paused = true`.
- **Position Awareness:** Won’t double-buy; exits only if holding.
- **Dry-Run Mode:** Evaluate signals without placing orders.

---

## Explainability & Audit Trail

- **Reason strings** (e.g., “BUY — SMA(10) crossed above SMA(30)”).
- **Confidence scores** (based on SMA separation).  
- **CSV log fields:** `timestamp, symbol, side, qty, status, filled_avg_price, reason, confidence`.

---

## Metrics

- **PnL** since first trade  
- **Sharpe (approx)** from returns  
- **Max Drawdown** from equity curve  
- **Equity & drawdown charts** in dashboard  

---

## Security Practices

- Never commit `.env`.  
- Regenerate secrets after demos.  
- Rotate keys periodically.  
- Avoid logging sensitive data.  
- Pin dependency versions for reproducibility.

---

## Operational Notes

- **Market hours:** US equities don’t fill when closed. Use crypto for 24/7 test fills.  
- **Rate limits:** Handle API 429 with backoff.  
- **State files:** Local only; move to DB in production.  

---

## Troubleshooting

- **“Missing ALPACA_* env vars”** → check `.env`.  
- **Order won’t fill** → market closed. Try crypto.  
- **Dashboard table instead of chart** → check plotting code.  
- **Pause not working** → ensure main loop checks `user_paused`.  

---

## Testing

- Backtest SMA signals on historical bars.  
- Submit paper orders, check `trade_log.csv`.  
- Verify auto-pause triggers when threshold is lowered.  

---

## Roadmap

- Add Sortino, win rate, expectancy.  
- ATR-based position sizing.  
- Strategy library (momentum, mean reversion).  
- WebSocket data feed.  
- Cloud deployment & CI/CD.  

---

## License

© 2025 Joe Tiller. All Rights Reserved.  

This project is provided solely for demonstration and educational purposes.  
No part of this codebase may be copied, modified, distributed, or used in any commercial application without prior written permission from the author.  

This software is not investment advice and carries no warranty of any kind. Use at your own risk.

