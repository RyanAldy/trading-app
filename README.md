# Trading Dashboard

A lightweight Python Dash trading dashboard connected to a Trading 212 practice (equity) account and an OANDA practice (forex) account. Built for day trading research, signal monitoring, and semi-automated order execution.

## Features

### Stock Screener
- Scans the top 250 day gainers via Yahoo Finance
- Filters by gain %, price range, market cap, and relative volume
- Computes indicators: VWAP, MACD, RSI, EMA 20/50, ATR, relative volume
- Clickable tiles open a detail modal with a 5-min intraday candlestick chart and full indicator breakdown
- One-click buy/sell orders via the Trading 212 API (equity account)

### Forex Tab
- Monitors 10 major/minor currency pairs in real time
- Session clock (London, New York, Tokyo, Sydney)
- Currency strength index — shows which currencies are leading or lagging
- Per-pair detail modal with:
  - 1H candlestick chart with EMA 20/50 overlay
  - RSI, MACD, ATR panels
  - Indicator descriptions for beginners
  - Live P&L calculator — adjust units and instantly see pips to SL/TP, pip value, profit and risk in quote currency, estimated margin, and R:R ratio
- Order placement via OANDA practice API with server-side SL/TP

### Auto-Trader Engine
- Background scanner runs every 2 minutes during US market hours (09:45–15:30 ET)
- Only surfaces signals where all 6 criteria are met simultaneously
- Semi-automatic: signals appear in the UI for manual confirmation before any order is placed
- Position sizing at 1% account risk per trade
- Exit monitor checks open positions every 60 seconds against SL/TP
- Daily P&L tracking with configurable profit target and loss limit

### Portfolio & News
- Live portfolio view pulled from Trading 212
- Financial news feed

## Setup

### Prerequisites
- Python 3.11+
- A [Trading 212](https://www.trading212.com) practice (Invest) account with API access enabled
- An [OANDA](https://www.oanda.com) practice account

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure environment variables

Copy the template below into a `.env` file in the project root. **Never commit this file.**

```env
# Trading 212 — Invest/ISA account (equities only)
T212_API_KEY_ID=your_t212_key_id
T212_API_KEY_SECRET=your_t212_key_secret
T212_IS_DEMO=true

# OANDA — forex CFD orders
OANDA_API_TOKEN=your_oanda_api_token
OANDA_ACCOUNT_ID=your_oanda_account_id
OANDA_IS_DEMO=true

# Screener filters
MIN_GAIN_PCT=10
MIN_MARKET_CAP=10000000
MIN_REL_VOLUME=1.0
MIN_PRICE=2.0
MAX_PRICE=20.0

# Auto-trader settings
RISK_PCT=0.01
DAILY_TARGET=50
DAILY_LOSS_LIMIT=50
AUTO_MIN_REL_VOL=1.5
```

**Getting your API keys:**
- **Trading 212**: Settings → API → Generate key (Invest account only — the T212 public API does not cover CFD/forex)
- **OANDA**: Log in → Manage Funds → API Access → Generate token. Your account ID is shown on the dashboard.

### Run

```bash
python3.11 app.py
```

Then open [http://127.0.0.1:8050](http://127.0.0.1:8050) in your browser.

## Project Structure

```
trading_dashboard/
├── app.py          # Dash UI, layout, and all callbacks
├── screener.py     # Data layer: Yahoo Finance, T212Client, OandaClient, forex indicators
├── trader.py       # Auto-trader engine (background threads, signal/exit logic)
├── requirements.txt
└── .env            # Credentials — never commit (excluded by .gitignore)
```

## Tech Stack

| Library | Purpose |
|---|---|
| [Dash](https://dash.plotly.com) | UI framework |
| [Plotly](https://plotly.com) | Interactive charts |
| [dash-bootstrap-components](https://dash-bootstrap-components.opensource.faculty.ai) | Layout and components |
| [yfinance](https://github.com/ranaroussi/yfinance) | Market data (stocks + forex) |
| [pandas](https://pandas.pydata.org) | Data manipulation and indicator calculation |
| [requests](https://docs.python-requests.org) | T212 and OANDA REST API calls |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | Environment variable management |

## Notes

- The Trading 212 public API covers the **Invest/ISA account only** (stocks and ETFs). Forex orders route through OANDA.
- The auto-trader runs in-process using daemon threads. Use a single worker if deploying with Gunicorn (`-w 1`).
- All market data is TTL-cached (290 seconds) to avoid rate limiting.
- This dashboard connects to **practice accounts only**. Do not point it at a live account without thorough testing.
