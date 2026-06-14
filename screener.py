import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

T212_IS_DEMO = os.getenv("T212_IS_DEMO", "true").lower() == "true"
T212_BASE_URL = (
    "https://demo.trading212.com/api/v0"
    if T212_IS_DEMO
    else "https://live.trading212.com/api/v0"
)
T212_API_KEY = os.getenv("T212_API_KEY_ID", "")
MIN_GAIN_PCT   = float(os.getenv("MIN_GAIN_PCT",    30))
MIN_MARKET_CAP = float(os.getenv("MIN_MARKET_CAP",  10_000_000))
MIN_REL_VOLUME = float(os.getenv("MIN_REL_VOLUME",  1.0))
MIN_PRICE      = float(os.getenv("MIN_PRICE",        2.0))
MAX_PRICE      = float(os.getenv("MAX_PRICE",       20.0))

SCREENER_COLS = [
    "Ticker", "Price", "Day Gain%", "Rel Vol", "Market Cap", "Stop Loss", "Take Profit",
]

WATCHLIST_COLS = [
    "Ticker", "Price", "Day Gain%", "Price OK", "Mkt Cap", "Missing",
]

_YF_HEADERS   = {"User-Agent": "Mozilla/5.0"}
_CACHE_TTL    = 290           # seconds — aligned with the 5-min auto-refresh
_compute_cache: dict = {}     # {ticker: (timestamp, result)}
_chart_cache:   dict = {}     # {ticker: (timestamp, result)}


class T212Client:
    _instruments_cache: list | None = None

    def __init__(self):
        self.session = requests.Session()
        key_id = os.getenv("T212_API_KEY_ID", "")
        key_secret = os.getenv("T212_API_KEY_SECRET", "")
        self.session.auth = (key_id, key_secret)
        self.session.headers.update({"Content-Type": "application/json"})
        self.base_url = T212_BASE_URL

    def get_account_info(self) -> dict:
        try:
            r = self.session.get(f"{self.base_url}/equity/account/cash", timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"free": 0.0, "total": 0.0, "currency": "USD", "error": str(e)}

    def get_portfolio(self) -> list:
        try:
            r = self.session.get(f"{self.base_url}/equity/portfolio", timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception:
            return []

    def get_instruments(self) -> list:
        """Fetch and cache the full T212 instruments list."""
        if T212Client._instruments_cache is None:
            try:
                r = self.session.get(
                    f"{self.base_url}/equity/metadata/instruments", timeout=30
                )
                r.raise_for_status()
                T212Client._instruments_cache = r.json()
            except Exception:
                T212Client._instruments_cache = []
        return T212Client._instruments_cache

    def find_ticker(self, yahoo_ticker: str) -> str | None:
        """Map a Yahoo Finance ticker to the T212 instrument ticker (e.g. AAPL → AAPL_US_EQ)."""
        upper = yahoo_ticker.upper()
        # Fast path: try the common US equity format first
        candidate = f"{upper}_US_EQ"
        instruments = self.get_instruments()
        for inst in instruments:
            if inst.get("ticker") == candidate:
                return candidate
        # Fallback: match on the first segment of the T212 ticker
        for inst in instruments:
            t = inst.get("ticker", "")
            if t.split("_")[0] == upper:
                return t
        return None

    def place_market_order(
        self,
        t212_ticker: str,
        quantity: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """Place a market order. Positive quantity = BUY, negative = SELL.
        Optional stop_loss and take_profit prices are sent to T212 so they
        manage the exit server-side — they trigger even if this app is closed.
        """
        body: dict = {"ticker": t212_ticker, "quantity": round(quantity, 8)}
        if stop_loss is not None:
            body["stopLoss"] = {"price": round(stop_loss, 6), "guaranteedStop": False}
        if take_profit is not None:
            body["takeProfit"] = {"price": round(take_profit, 6)}
        try:
            r = self.session.post(
                f"{self.base_url}/equity/orders/market",
                json=body,
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            detail = ""
            try:
                detail = r.text  # type: ignore[possibly-undefined]
            except Exception:
                pass
            return {"error": str(e), "detail": detail}

    def get_positions_map(self) -> dict:
        """Return {yahoo_ticker: {quantity, avg_price, current_price}} for all open positions."""
        try:
            positions = self.get_portfolio()
            result = {}
            for pos in positions:
                t212_tick = pos.get("ticker", "")
                yahoo = t212_tick.split("_")[0]
                result[yahoo] = {
                    "quantity":      float(pos.get("quantity",     0) or 0),
                    "avg_price":     float(pos.get("averagePrice", 0) or 0),
                    "current_price": float(pos.get("currentPrice", 0) or 0),
                }
            return result
        except Exception:
            return {}

    def close_position(self, t212_ticker: str, quantity: float) -> dict:
        """Sell quantity shares (positive value — method negates internally)."""
        return self.place_market_order(t212_ticker, -abs(quantity))

    def find_forex_ticker(self, pair_label: str) -> str | None:
        """Find T212 instrument ticker for a forex pair like 'EUR/USD'."""
        normalized = pair_label.replace("/", "").upper()
        instruments = self.get_instruments()
        for inst in instruments:
            if inst.get("ticker", "").upper() == normalized:
                return inst["ticker"]
        for inst in instruments:
            t = inst.get("ticker", "").upper()
            if t.startswith(normalized):
                return inst["ticker"]
        return None


# ── OANDA forex client ────────────────────────────────────────────────────────

class OandaClient:
    """REST client for the OANDA v20 API (practice or live)."""

    def __init__(self):
        token    = os.getenv("OANDA_API_TOKEN", "")
        is_demo  = os.getenv("OANDA_IS_DEMO", "true").lower() == "true"
        self.account_id = os.getenv("OANDA_ACCOUNT_ID", "")
        self.base_url   = (
            "https://api-fxpractice.oanda.com/v3"
            if is_demo
            else "https://api-fxtrade.oanda.com/v3"
        )
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        })

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def yf_to_instrument(yf_sym: str) -> str:
        """Convert yfinance symbol to OANDA instrument. EURUSD=X → EUR_USD."""
        sym = yf_sym.replace("=X", "").upper()
        return sym[:3] + "_" + sym[3:] if len(sym) == 6 else sym

    # ── Account ───────────────────────────────────────────────────────────────

    def get_account_summary(self) -> dict:
        """Return account dict: balance, currency, NAV, openTradeCount, etc."""
        try:
            r = self.session.get(
                f"{self.base_url}/accounts/{self.account_id}/summary", timeout=10
            )
            r.raise_for_status()
            return r.json().get("account", {})
        except Exception as e:
            return {"error": str(e)}

    # ── Trading ───────────────────────────────────────────────────────────────

    def place_market_order(
        self,
        instrument: str,
        units: float,
        stop_loss: float | None  = None,
        take_profit: float | None = None,
    ) -> dict:
        """Place a MARKET order.  units > 0 = BUY, < 0 = SELL.
        stop_loss and take_profit are prices (not distances).
        """
        is_jpy  = "JPY" in instrument
        decimals = 3 if is_jpy else 5

        order: dict = {
            "type":         "MARKET",
            "instrument":   instrument,
            "units":        str(int(units)),
            "timeInForce":  "FOK",
            "positionFill": "DEFAULT",
        }
        if stop_loss is not None:
            order["stopLossOnFill"] = {
                "price":       f"{stop_loss:.{decimals}f}",
                "timeInForce": "GTC",
            }
        if take_profit is not None:
            order["takeProfitOnFill"] = {
                "price":       f"{take_profit:.{decimals}f}",
                "timeInForce": "GTC",
            }

        try:
            r = self.session.post(
                f"{self.base_url}/accounts/{self.account_id}/orders",
                json={"order": order},
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            detail = ""
            try:
                detail = r.text  # type: ignore[possibly-undefined]
            except Exception:
                pass
            return {"error": str(e), "detail": detail}

    def get_market_status(self, instruments: list) -> dict:
        """Return {instrument: is_tradeable} for the given OANDA instruments."""
        params = "instruments=" + ",".join(instruments)
        try:
            r = self.session.get(
                f"{self.base_url}/accounts/{self.account_id}/pricing?{params}",
                timeout=10,
            )
            r.raise_for_status()
            return {
                p["instrument"]: bool(p.get("tradeable", False))
                for p in r.json().get("prices", [])
            }
        except Exception:
            return {}

    def get_open_trades(self) -> list:
        """Return list of open trade dicts from OANDA."""
        try:
            r = self.session.get(
                f"{self.base_url}/accounts/{self.account_id}/openTrades", timeout=10
            )
            r.raise_for_status()
            return r.json().get("trades", [])
        except Exception:
            return []

    def close_trade(self, trade_id: str) -> dict:
        """Close a specific open trade by OANDA trade ID."""
        try:
            r = self.session.put(
                f"{self.base_url}/accounts/{self.account_id}/trades/{trade_id}/close",
                timeout=15,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": str(e)}


def get_top_gainers(n: int = 250) -> list:
    url = (
        "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
        f"?scrIds=day_gainers&count={n}"
    )
    try:
        r = requests.get(url, headers=_YF_HEADERS, timeout=15)
        r.raise_for_status()
        quotes = r.json()["finance"]["result"][0]["quotes"]
    except Exception:
        return []

    tickers = []
    for q in quotes:
        sym = q.get("symbol", "")
        pct = q.get("regularMarketChangePercent", 0)
        if "." in sym or sym.startswith("^"):
            continue
        if pct >= MIN_GAIN_PCT:
            tickers.append(sym)
    return tickers


def get_all_gainers(n: int = 250) -> list:
    """Return all day gainers from Yahoo Finance with basic display info — no criteria filter."""
    url = (
        "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
        f"?scrIds=day_gainers&count={n}"
    )
    try:
        r = requests.get(url, headers=_YF_HEADERS, timeout=15)
        r.raise_for_status()
        quotes = r.json()["finance"]["result"][0]["quotes"]
    except Exception:
        return []

    gainers = []
    for q in quotes:
        sym = q.get("symbol", "")
        if "." in sym or sym.startswith("^"):
            continue
        cap = q.get("marketCap", 0) or 0
        gainers.append({
            "ticker":       sym,
            "name":         q.get("shortName", sym),
            "price":        q.get("regularMarketPrice", 0) or 0,
            "day_gain_pct": q.get("regularMarketChangePercent", 0) or 0,
            "volume":       q.get("regularMarketVolume", 0) or 0,
            "market_cap":   cap,
        })
    return sorted(gainers, key=lambda x: x["day_gain_pct"], reverse=True)


def _safe_float(val, default=0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def compute_indicators(ticker: str) -> dict | None:
    now = time.time()
    if ticker in _compute_cache:
        ts, cached = _compute_cache[ticker]
        if now - ts < _CACHE_TTL:
            return cached

    try:
        df = yf.download(
            ticker, period="5d", interval="5m",
            progress=False, auto_adjust=True,
        )
        # yfinance sometimes returns MultiIndex columns even for single ticker
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        if df.empty:
            return None

        # Slice to the most recent trading day so VWAP resets correctly
        last_date = df.index[-1].date()
        df = df[df.index.date == last_date]
        if len(df) < 26:
            return None

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        vol = df["Volume"]

        # VWAP
        typical = (high + low + close) / 3
        vwap = (typical * vol).cumsum() / vol.cumsum()
        vwap_bullish = bool(close.iloc[-1] > vwap.iloc[-1])

        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal = macd_line.ewm(span=9, adjust=False).mean()
        macd_bullish = bool(macd_line.iloc[-1] > signal.iloc[-1])

        current_price = _safe_float(close.iloc[-1])
        day_low = _safe_float(low.min())
        today_vol = _safe_float(vol.sum())

        # 20-day average volume
        hist = yf.download(
            ticker, period="21d", interval="1d",
            progress=False, auto_adjust=True,
        )
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.droplevel(1)

        avg_vol = _safe_float(hist["Volume"].iloc[:-1].mean()) if len(hist) > 1 else 1.0
        rel_volume = today_vol / avg_vol if avg_vol > 0 else 0.0

        # Market cap and previous close via fast_info
        fi = yf.Ticker(ticker).fast_info
        market_cap = _safe_float(getattr(fi, "market_cap", None))
        prev_close = _safe_float(getattr(fi, "previous_close", None))

        if prev_close <= 0:
            prev_close = _safe_float(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price

        day_gain_pct = (
            (current_price - prev_close) / prev_close * 100 if prev_close > 0 else 0.0
        )

        result = {
            "ticker": ticker,
            "current_price": current_price,
            "prev_close": prev_close,
            "day_gain_pct": day_gain_pct,
            "vwap_bullish": vwap_bullish,
            "macd_bullish": macd_bullish,
            "rel_volume": rel_volume,
            "market_cap": market_cap,
            "day_low": day_low,
        }
        _compute_cache[ticker] = (time.time(), result)
        return result
    except Exception:
        return None


def calc_stop_take(entry: float, day_low: float) -> tuple:
    stop_loss = day_low if (0 < day_low < entry) else entry * 0.95
    risk = entry - stop_loss
    take_profit = entry + 2 * risk
    return round(stop_loss, 2), round(take_profit, 2)


def _fmt_cap(v: float) -> str:
    if v >= 1e9:
        return f"${v/1e9:.1f}B"
    if v >= 1e6:
        return f"${v/1e6:.0f}M"
    return f"${v:,.0f}"


def screen_stocks() -> tuple:
    """Returns (passing_df, watchlist_df).

    passing_df  — stocks meeting all 5 criteria, top 10 by day gain.
    watchlist_df — stocks up >=30% but failing one or more other criteria.
    """
    empty_pass  = pd.DataFrame(columns=SCREENER_COLS)
    empty_watch = pd.DataFrame(columns=WATCHLIST_COLS)

    tickers = get_top_gainers(50)
    if not tickers:
        return empty_pass, empty_watch

    passing   = []
    watchlist = []

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(compute_indicators, t): t for t in tickers}
        for fut in as_completed(futures):
            data = fut.result()
            if data is None:
                continue

            gain_ok = data["day_gain_pct"] >= MIN_GAIN_PCT
            if not gain_ok:
                continue  # below gain threshold — exclude entirely

            price_ok = MIN_PRICE <= data["current_price"] <= MAX_PRICE

            if price_ok:
                passing.append(data)
            else:
                data["_missing"] = f"Price ${data['current_price']:.2f} outside ${MIN_PRICE:.0f}–${MAX_PRICE:.0f}"
                watchlist.append(data)

    # ── Build passing DataFrame ────────────────────────────────────────────
    passing_rows = []
    for d in sorted(passing, key=lambda x: x["day_gain_pct"], reverse=True)[:10]:
        sl, tp = calc_stop_take(d["current_price"], d["day_low"])
        entry = d["current_price"]
        passing_rows.append({
            "Ticker":      d["ticker"],
            "Price":       f"${entry:.2f}",
            "Day Gain%":   f"{d['day_gain_pct']:+.1f}%",
            "Rel Vol":     f"{d['rel_volume']:.1f}x",   # info only — not a filter criterion
            "Market Cap":  _fmt_cap(d["market_cap"]),
            "Stop Loss":   f"${sl:.2f} ({(sl - entry) / entry * 100:+.1f}%)",
            "Take Profit": f"${tp:.2f} ({(tp - entry) / entry * 100:+.1f}%)",
        })

    # ── Build watchlist DataFrame ──────────────────────────────────────────
    watchlist_rows = []
    for d in sorted(watchlist, key=lambda x: x["day_gain_pct"], reverse=True):
        entry = d["current_price"]
        watchlist_rows.append({
            "Ticker":    d["ticker"],
            "Price":     f"${entry:.2f}",
            "Day Gain%": f"{d['day_gain_pct']:+.1f}%",
            "Price OK":  "✓" if MIN_PRICE <= entry <= MAX_PRICE  else "✗",
            "Mkt Cap":   "✓" if d["market_cap"] > MIN_MARKET_CAP else "✗",  # indicator only
            "Missing":   d["_missing"],
        })

    df_pass  = pd.DataFrame(passing_rows)  if passing_rows  else empty_pass
    df_watch = pd.DataFrame(watchlist_rows) if watchlist_rows else empty_watch
    return df_pass, df_watch


def get_stock_detail(ticker: str) -> dict:
    """Return all six indicator values and pass/fail status for any ticker."""
    data = compute_indicators(ticker)
    if data is None:
        return {"ticker": ticker, "error": True, "current_price": 0}

    entry = data["current_price"]
    sl, tp = calc_stop_take(entry, data["day_low"])

    return {
        "ticker":        ticker,
        "error":         False,
        "current_price": entry,
        "day_gain_pct":  data["day_gain_pct"],
        "rel_volume":    data["rel_volume"],
        "market_cap":    data["market_cap"],
        "vwap_bullish":  data["vwap_bullish"],
        "macd_bullish":  data["macd_bullish"],
        "day_low":       data["day_low"],
        "stop_loss":     sl,
        "take_profit":   tp,
        # Criteria pass/fail
        "gain_ok":       data["day_gain_pct"] >= MIN_GAIN_PCT,
        "price_ok":      MIN_PRICE <= entry <= MAX_PRICE,
        "cap_ok":        data["market_cap"] > MIN_MARKET_CAP,
        "vol_high":      data["rel_volume"] >= MIN_REL_VOLUME,
    }


def get_chart_data(ticker: str) -> dict | None:
    """Fetch 5-min intraday OHLCV and compute VWAP + MACD for charting."""
    now = time.time()
    if ticker in _chart_cache:
        ts, cached = _chart_cache[ticker]
        if now - ts < _CACHE_TTL:
            return cached

    try:
        df = yf.download(ticker, period="5d", interval="5m", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        if df.empty:
            return None

        # Slice to the most recent trading day so VWAP resets correctly
        last_date = df.index[-1].date()
        df = df[df.index.date == last_date]
        if len(df) < 26:
            return None

        close = df["Close"]
        high  = df["High"]
        low   = df["Low"]
        vol   = df["Volume"]

        typical = (high + low + close) / 3
        vwap = (typical * vol).cumsum() / vol.cumsum()

        ema12     = close.ewm(span=12, adjust=False).mean()
        ema26     = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal    = macd_line.ewm(span=9, adjust=False).mean()
        hist      = macd_line - signal

        result = {
            "times":  [str(t) for t in df.index.tolist()],
            "open":   df["Open"].tolist(),
            "high":   high.tolist(),
            "low":    low.tolist(),
            "close":  close.tolist(),
            "volume": vol.tolist(),
            "vwap":   vwap.tolist(),
            "macd":   macd_line.tolist(),
            "signal": signal.tolist(),
            "hist":   hist.tolist(),
        }
        _chart_cache[ticker] = (time.time(), result)
        return result
    except Exception:
        return None


def screen_stocks_for_engine(min_rel_vol: float | None = None) -> list:
    """Return raw indicator dicts passing ALL 6 entry criteria for the auto-trader.

    Criteria: gain ≥ MIN_GAIN_PCT, price in range, VWAP bullish, MACD bullish,
    rel_volume ≥ min_rel_vol, market_cap ≥ MIN_MARKET_CAP.
    Each dict includes stop_loss and take_profit.
    """
    if min_rel_vol is None:
        min_rel_vol = float(os.getenv("AUTO_MIN_REL_VOL", 1.5))

    tickers = get_top_gainers(50)
    if not tickers:
        return []

    passing = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(compute_indicators, t): t for t in tickers}
        for fut in as_completed(futures):
            data = fut.result()
            if data is None:
                continue
            if (
                data["day_gain_pct"] >= MIN_GAIN_PCT
                and MIN_PRICE <= data["current_price"] <= MAX_PRICE
                and data["vwap_bullish"]
                and data["macd_bullish"]
                and data["rel_volume"] >= min_rel_vol
                and data["market_cap"] >= MIN_MARKET_CAP
            ):
                sl, tp = calc_stop_take(data["current_price"], data["day_low"])
                passing.append({**data, "stop_loss": sl, "take_profit": tp})

    return passing


def get_news(ticker: str) -> list:
    try:
        items = yf.Ticker(ticker).news or []
        news = []
        for item in items[:3]:
            content = item.get("content", {})
            title = content.get("title") or item.get("title", "No title")
            link = (
                content.get("canonicalUrl", {}).get("url")
                or item.get("link", "#")
            )
            publisher = (
                content.get("provider", {}).get("displayName")
                or item.get("publisher", "")
            )
            news.append({"title": title, "link": link, "publisher": publisher})
        return news
    except Exception:
        return []


# ── Forex ──────────────────────────────────────────────────────────────────────

FOREX_PAIRS = [
    {"label": "EUR/USD", "yf": "EURUSD=X", "base": "EUR", "quote": "USD"},
    {"label": "GBP/USD", "yf": "GBPUSD=X", "base": "GBP", "quote": "USD"},
    {"label": "USD/JPY", "yf": "USDJPY=X", "base": "USD", "quote": "JPY"},
    {"label": "AUD/USD", "yf": "AUDUSD=X", "base": "AUD", "quote": "USD"},
    {"label": "USD/CAD", "yf": "USDCAD=X", "base": "USD", "quote": "CAD"},
    {"label": "USD/CHF", "yf": "USDCHF=X", "base": "USD", "quote": "CHF"},
    {"label": "NZD/USD", "yf": "NZDUSD=X", "base": "NZD", "quote": "USD"},
    {"label": "EUR/GBP", "yf": "EURGBP=X", "base": "EUR", "quote": "GBP"},
    {"label": "GBP/JPY", "yf": "GBPJPY=X", "base": "GBP", "quote": "JPY"},
    {"label": "EUR/JPY", "yf": "EURJPY=X", "base": "EUR", "quote": "JPY"},
]

_forex_cache: dict = {}


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.where(avg_loss != 0, 1e-10)
    return 100 - (100 / (1 + rs))


def _to_list(s: pd.Series) -> list:
    return [None if pd.isna(v) else float(v) for v in s]


def _get_or_fetch_forex(yf_sym: str) -> dict | None:
    """Download 5d 1H data for a forex pair, compute all indicators, TTL-cache the result."""
    now = time.time()
    if yf_sym in _forex_cache:
        ts, cached = _forex_cache[yf_sym]
        if now - ts < _CACHE_TTL:
            return cached

    try:
        df = yf.download(yf_sym, period="5d", interval="1h", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        if len(df) < 50:
            return None

        close = df["Close"]
        high  = df["High"]
        low   = df["Low"]

        ema20     = close.ewm(span=20, adjust=False).mean()
        ema50     = close.ewm(span=50, adjust=False).mean()
        ema12     = close.ewm(span=12, adjust=False).mean()
        ema26     = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        macd_sig  = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - macd_sig
        rsi_s     = _rsi(close)

        tr  = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()

        current_price  = _safe_float(close.iloc[-1])
        price_24h      = _safe_float(close.iloc[max(0, len(close) - 25)])
        day_change_pct = (current_price - price_24h) / price_24h * 100 if price_24h else 0.0

        result = {
            "current_price":  current_price,
            "day_change_pct": round(day_change_pct, 4),
            "ema_bullish":    bool(ema20.iloc[-1] > ema50.iloc[-1]),
            "macd_bullish":   bool(macd_line.iloc[-1] > macd_sig.iloc[-1]),
            "rsi":            round(_safe_float(rsi_s.iloc[-1]), 2),
            "atr":            round(_safe_float(atr.iloc[-1]), 6),
            # Full series for chart rendering
            "times":          [str(t) for t in df.index.tolist()],
            "open":           _to_list(df["Open"]),
            "high":           _to_list(high),
            "low":            _to_list(low),
            "close":          _to_list(close),
            "ema20":          _to_list(ema20),
            "ema50":          _to_list(ema50),
            "rsi_series":     _to_list(rsi_s),
            "macd_line":      _to_list(macd_line),
            "macd_signal":    _to_list(macd_sig),
            "macd_hist":      _to_list(macd_hist),
        }
        _forex_cache[yf_sym] = (time.time(), result)
        return result
    except Exception:
        return None


def get_forex_overview() -> list:
    """Return lightweight summary dicts for all major pairs (used for tiles)."""
    cache_key = "__fx_ov__"
    now = time.time()
    if cache_key in _forex_cache:
        ts, cached = _forex_cache[cache_key]
        if now - ts < _CACHE_TTL:
            return cached

    results = []

    def _fetch(p):
        d = _get_or_fetch_forex(p["yf"])
        if d is None:
            return None
        return {
            "label": p["label"], "yf": p["yf"],
            "base":  p["base"],  "quote": p["quote"],
            "current_price":  d["current_price"],
            "day_change_pct": d["day_change_pct"],
            "ema_bullish":    d["ema_bullish"],
            "macd_bullish":   d["macd_bullish"],
            "rsi":            d["rsi"],
            "atr":            d["atr"],
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch, p): p for p in FOREX_PAIRS}
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                results.append(r)

    order = {p["yf"]: i for i, p in enumerate(FOREX_PAIRS)}
    results.sort(key=lambda x: order.get(x["yf"], 999))
    _forex_cache[cache_key] = (time.time(), results)
    return results


def get_forex_detail(yf_sym: str) -> dict:
    """Full indicator analysis for the forex modal."""
    d = _get_or_fetch_forex(yf_sym)
    if d is None:
        return {"error": True}

    pair_info = next((p for p in FOREX_PAIRS if p["yf"] == yf_sym), None)
    if not pair_info:
        return {"error": True}

    entry    = d["current_price"]
    atr      = d["atr"]
    is_jpy   = "JPY" in yf_sym
    pip_size = 0.01 if is_jpy else 0.0001
    decimals = 3   if is_jpy else 5
    atr_pips = int(atr / pip_size) if pip_size else 0

    return {
        "error":          False,
        "label":          pair_info["label"],
        "yf":             yf_sym,
        "base":           pair_info["base"],
        "quote":          pair_info["quote"],
        "current_price":  entry,
        "day_change_pct": d["day_change_pct"],
        "rsi":            d["rsi"],
        "rsi_bullish":    45 < d["rsi"] < 70,
        "ema_bullish":    d["ema_bullish"],
        "macd_bullish":   d["macd_bullish"],
        "atr":            atr,
        "atr_pips":       atr_pips,
        "pip_size":       pip_size,
        "stop_loss":      round(entry - atr, decimals),
        "take_profit":    round(entry + 2 * atr, decimals),
    }


def get_economic_calendar() -> list:
    """Fetch this week's High/Medium impact forex events from ForexFactory."""
    cache_key = "__calendar__"
    now = time.time()
    if cache_key in _forex_cache:
        ts, cached = _forex_cache[cache_key]
        if now - ts < 1800:  # 30-minute TTL — calendar doesn't change often
            return cached
    try:
        r = requests.get(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            headers=_YF_HEADERS, timeout=10,
        )
        r.raise_for_status()
        events = [e for e in r.json() if e.get("impact") in ("High", "Medium")]
        events.sort(key=lambda x: x.get("date", ""))
        _forex_cache[cache_key] = (time.time(), events)
        return events
    except Exception:
        return []


def compute_currency_strength(pairs: list) -> list:
    """Return list of {currency, score} sorted strongest → weakest."""
    CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
    scores = {c: 0.0 for c in CURRENCIES}
    counts = {c: 0   for c in CURRENCIES}
    for p in pairs:
        change = p.get("day_change_pct", 0.0)
        for key, sign in [(p.get("base", ""), 1), (p.get("quote", ""), -1)]:
            if key in scores:
                scores[key] += sign * change
                counts[key] += 1
    result = [
        {"currency": c, "score": round(scores[c] / counts[c], 4) if counts[c] else 0.0}
        for c in CURRENCIES
    ]
    result.sort(key=lambda x: x["score"], reverse=True)
    return result
