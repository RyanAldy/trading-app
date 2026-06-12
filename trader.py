import copy
import datetime
import math
import os
import threading
import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

RISK_PCT         = float(os.getenv("RISK_PCT",          0.01))
DAILY_TARGET     = float(os.getenv("DAILY_TARGET",      50.0))
DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT",  50.0))
AUTO_MIN_REL_VOL = float(os.getenv("AUTO_MIN_REL_VOL",  1.5))
SIGNAL_TTL_SECS  = 600   # auto-dismiss pending signals older than 10 min

ET = ZoneInfo("America/New_York")

_lock: threading.Lock = threading.Lock()

_state: dict = {
    "running":               False,
    "market_open":           False,
    "daily_realized_pnl":    0.0,
    "daily_target_hit":      False,
    "daily_loss_limit_hit":  False,
    "pending_signals":       {},   # {ticker: signal_dict}
    "open_trades":           {},   # {ticker: trade_dict}
    "_exiting":              set(),
    "trade_log":             [],
    "last_error":            "",
    "last_scan_at":          "",
    "last_monitor_at":       "",
}

_trader_instance: "AutoTrader | None" = None


class AutoTrader:

    def __init__(self):
        # Deferred import to avoid circular dependency at module load time
        from screener import T212Client
        self._t212 = T212Client()
        self._scan_thread:    threading.Thread | None = None
        self._monitor_thread: threading.Thread | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Start background threads. Idempotent."""
        with _lock:
            if _state["running"]:
                return
            _state["running"] = True

        self._scan_thread = threading.Thread(
            target=self._scan_loop, daemon=True, name="auto-scan"
        )
        self._monitor_thread = threading.Thread(
            target=self._exit_monitor_loop, daemon=True, name="exit-monitor"
        )
        self._scan_thread.start()
        self._monitor_thread.start()

    def stop(self):
        """Signal threads to exit on their next sleep cycle."""
        with _lock:
            _state["running"] = False

    def confirm_signal(self, ticker: str) -> str:
        """Place a market buy for a pending signal. Returns 'ok' or an error string."""
        with _lock:
            signal = _state["pending_signals"].get(ticker)
        if not signal:
            return "signal_not_found"

        result = self._t212.place_market_order(
            signal["t212_ticker"], signal["suggested_qty"]
        )
        if "error" in result:
            return result["error"]

        trade = {
            "ticker":       ticker,
            "t212_ticker":  signal["t212_ticker"],
            "entry_price":  signal["entry_price"],
            "stop_loss":    signal["stop_loss"],
            "take_profit":  signal["take_profit"],
            "quantity":     signal["suggested_qty"],
            "confirmed_at": datetime.datetime.now(ET).strftime("%H:%M:%S"),
            "order_id":     str(result.get("id", "—")),
        }
        with _lock:
            _state["open_trades"][ticker] = trade
            _state["pending_signals"].pop(ticker, None)
        return "ok"

    def dismiss_signal(self, ticker: str):
        with _lock:
            _state["pending_signals"].pop(ticker, None)

    def get_state(self) -> dict:
        """Thread-safe deep-copy snapshot, safe to serialise to JSON."""
        with _lock:
            snapshot = copy.deepcopy(_state)
        # Convert set to list for JSON serialisation
        snapshot["_exiting"] = list(snapshot.get("_exiting", set()))
        return snapshot

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _is_market_open() -> bool:
        now = datetime.datetime.now(ET).time()
        return datetime.time(9, 45) <= now < datetime.time(15, 30)

    # ── Scan loop ─────────────────────────────────────────────────────────────

    def _scan_loop(self):
        while True:
            with _lock:
                if not _state["running"]:
                    break

            market_open = self._is_market_open()
            with _lock:
                _state["market_open"] = market_open

            if not market_open:
                time.sleep(30)
                continue

            with _lock:
                limit_hit  = _state["daily_loss_limit_hit"]
                target_hit = _state["daily_target_hit"]
                existing   = set(_state["open_trades"]) | set(_state["pending_signals"])

            if limit_hit or target_hit:
                time.sleep(60)
                continue

            # Network calls outside the lock
            try:
                balance    = float(self._t212.get_account_info().get("free", 0) or 0)
                candidates = _screen()
            except Exception as exc:
                with _lock:
                    _state["last_error"] = f"Scan error: {exc}"
                time.sleep(120)
                continue

            new_signals: dict = {}
            for data in candidates:
                ticker = data["ticker"]
                if ticker in existing:
                    continue
                t212_ticker = self._t212.find_ticker(ticker)
                if not t212_ticker:
                    continue
                entry         = data["current_price"]
                stop_distance = entry - data["stop_loss"]
                if stop_distance <= 0:
                    stop_distance = entry * 0.05
                risk_usd = balance * RISK_PCT if balance > 0 else 10.0
                qty      = math.floor(risk_usd / stop_distance)
                if qty < 1:
                    continue
                new_signals[ticker] = {
                    "ticker":        ticker,
                    "t212_ticker":   t212_ticker,
                    "entry_price":   round(entry, 4),
                    "stop_loss":     data["stop_loss"],
                    "take_profit":   data["take_profit"],
                    "suggested_qty": qty,
                    "risk_usd":      round(risk_usd, 2),
                    "rel_volume":    round(data["rel_volume"], 2),
                    "day_gain_pct":  round(data["day_gain_pct"], 2),
                    "generated_at":  datetime.datetime.now(ET).isoformat(),
                }

            cutoff = (
                datetime.datetime.now(ET) - datetime.timedelta(seconds=SIGNAL_TTL_SECS)
            ).isoformat()

            with _lock:
                # Auto-dismiss stale pending signals
                stale = [
                    t for t, s in _state["pending_signals"].items()
                    if s["generated_at"] < cutoff
                ]
                for t in stale:
                    _state["pending_signals"].pop(t, None)
                # Add new signals (never overwrite an already-open trade)
                for t, sig in new_signals.items():
                    if t not in _state["open_trades"]:
                        _state["pending_signals"][t] = sig
                _state["last_scan_at"] = datetime.datetime.now(ET).strftime("%H:%M:%S")
                _state["last_error"]   = ""

            time.sleep(120)

    # ── Exit monitor loop ─────────────────────────────────────────────────────

    def _exit_monitor_loop(self):
        while True:
            with _lock:
                if not _state["running"]:
                    break
                trades_snapshot = dict(_state["open_trades"])
                exiting_now     = set(_state["_exiting"])

            for ticker, trade in trades_snapshot.items():
                if ticker in exiting_now:
                    continue

                # Fetch current price: T212 portfolio first, then cached yfinance
                current_price = self._get_current_price(ticker)
                if not current_price:
                    continue

                exit_reason: str | None = None
                if current_price <= trade["stop_loss"]:
                    exit_reason = "SL"
                elif current_price >= trade["take_profit"]:
                    exit_reason = "TP"

                if not exit_reason:
                    continue

                # Claim the trade before calling T212 (prevents double-exit)
                with _lock:
                    _state["_exiting"].add(ticker)

                result = self._t212.close_position(trade["t212_ticker"], trade["quantity"])

                if "error" in result:
                    with _lock:
                        _state["_exiting"].discard(ticker)
                        _state["last_error"] = f"Exit {ticker} failed: {result['error']}"
                    continue

                pnl = (current_price - trade["entry_price"]) * trade["quantity"]
                log_entry = {
                    "ticker":      ticker,
                    "entry_price": trade["entry_price"],
                    "exit_price":  round(current_price, 4),
                    "quantity":    trade["quantity"],
                    "pnl":         round(pnl, 2),
                    "exit_reason": exit_reason,
                    "closed_at":   datetime.datetime.now(ET).strftime("%H:%M:%S"),
                }
                with _lock:
                    _state["open_trades"].pop(ticker, None)
                    _state["_exiting"].discard(ticker)
                    _state["trade_log"].append(log_entry)
                    _state["daily_realized_pnl"] = round(
                        _state["daily_realized_pnl"] + pnl, 2
                    )
                    if _state["daily_realized_pnl"] >= DAILY_TARGET:
                        _state["daily_target_hit"] = True
                    if _state["daily_realized_pnl"] <= -abs(DAILY_LOSS_LIMIT):
                        _state["daily_loss_limit_hit"] = True

            with _lock:
                _state["last_monitor_at"] = datetime.datetime.now(ET).strftime("%H:%M:%S")

            time.sleep(60)

    def _get_current_price(self, ticker: str) -> float | None:
        """Try T212 portfolio price first, fall back to cached yfinance."""
        try:
            pos_map = self._t212.get_positions_map()
            price   = pos_map.get(ticker, {}).get("current_price", 0.0)
            if price and price > 0:
                return float(price)
        except Exception:
            pass
        try:
            from screener import compute_indicators
            ind = compute_indicators(ticker)
            if ind:
                return float(ind["current_price"])
        except Exception:
            pass
        return None


def _screen() -> list:
    """Deferred import wrapper to avoid circular imports at load time."""
    from screener import screen_stocks_for_engine
    return screen_stocks_for_engine(AUTO_MIN_REL_VOL)


def get_trader() -> AutoTrader:
    """Return the module-level singleton, creating it if necessary."""
    global _trader_instance
    if _trader_instance is None:
        _trader_instance = AutoTrader()
    return _trader_instance
