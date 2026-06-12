import dash
from dash import Dash, dcc, html, dash_table, Input, Output, State, callback, ctx
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from screener import (
    T212Client, OandaClient, screen_stocks, get_news, get_chart_data,
    get_all_gainers, get_stock_detail, _fmt_cap,
    MIN_GAIN_PCT, MIN_PRICE, MAX_PRICE, MIN_MARKET_CAP, MIN_REL_VOLUME,
    get_forex_overview, get_forex_detail, get_economic_calendar,
    compute_currency_strength, FOREX_PAIRS, _get_or_fetch_forex,
)
from trader import get_trader, DAILY_TARGET, DAILY_LOSS_LIMIT, RISK_PCT

# ── Colour tokens ─────────────────────────────────────────────────────────────
C = {
    "bg":      "#09090f",
    "sidebar": "#0d0e18",
    "card":    "#111220",
    "row_alt": "#0c0d18",
    "border":  "#1c1d2e",
    "green":   "#00e676",
    "amber":   "#f59e0b",
    "red":     "#f87171",
    "blue":    "#3b82f6",
    "txt":     "#f1f5f9",
    "muted":   "#6b7280",
    "dim":     "#2d3047",
}

FONT = "Inter, system-ui, -apple-system, sans-serif"

app = Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap",
    ],
    suppress_callback_exceptions=True,
)
app.title = "T212 Scanner"
t212  = T212Client()
oanda = OandaClient()   # handles all forex CFD orders via OANDA practice API

_auto_trader = get_trader()
_auto_trader.start()

# ── Shared style dicts ────────────────────────────────────────────────────────

CARD = {
    "backgroundColor": C["card"],
    "border": f"1px solid {C['border']}",
    "borderRadius": "12px",
    "padding": "24px",
    "marginBottom": "24px",
}

TBL_CELL = {
    "backgroundColor": C["card"],
    "color": C["txt"],
    "textAlign": "left",
    "fontSize": "13px",
    "padding": "12px 16px",
    "border": f"1px solid {C['border']}",
    "fontFamily": FONT,
}

TBL_HDR = {
    "backgroundColor": "#090a13",
    "color": C["muted"],
    "fontWeight": "600",
    "textAlign": "left",
    "fontSize": "11px",
    "textTransform": "uppercase",
    "letterSpacing": "0.06em",
    "border": f"1px solid {C['border']}",
    "padding": "10px 16px",
    "fontFamily": FONT,
}

SCREENER_TABLE_COLS = [
    {"name": "Ticker",      "id": "Ticker"},
    {"name": "Price",       "id": "Price"},
    {"name": "Day Gain %",  "id": "Day Gain%"},
    {"name": "Rel Vol",     "id": "Rel Vol"},
    {"name": "Market Cap",  "id": "Market Cap"},
    {"name": "Stop Loss",   "id": "Stop Loss"},
    {"name": "Take Profit", "id": "Take Profit"},
    {"name": "Signal",      "id": "Trade?"},
]

WATCHLIST_TABLE_COLS = [
    {"name": "Ticker",      "id": "Ticker"},
    {"name": "Price",       "id": "Price"},
    {"name": "Day Gain%",   "id": "Day Gain%"},
    {"name": "Price $2–$20","id": "Price OK"},
    {"name": "Mkt Cap",     "id": "Mkt Cap"},
    {"name": "Missing",     "id": "Missing"},
]

PORTFOLIO_COLS = [
    {"name": "Symbol",   "id": "ticker"},
    {"name": "Qty",      "id": "quantity"},
    {"name": "Price",    "id": "currentPrice"},
    {"name": "Avg Cost", "id": "averagePrice"},
    {"name": "P&L",      "id": "ppl"},
]

PAGES = ["dashboard", "screener", "universe", "portfolio", "news", "forex", "auto", "settings"]

# ── Nav helpers ───────────────────────────────────────────────────────────────

def _nav_style(active: bool) -> dict:
    return {
        "display": "flex",
        "alignItems": "center",
        "gap": "12px",
        "padding": "10px 16px",
        "margin": "1px 8px",
        "borderRadius": "8px",
        "fontSize": "14px",
        "fontWeight": "500",
        "color": C["green"] if active else C["muted"],
        "backgroundColor": f"{C['green']}12" if active else "transparent",
        "borderLeft": f"3px solid {C['green']}" if active else "3px solid transparent",
        "cursor": "pointer",
        "userSelect": "none",
        "transition": "all 0.15s ease",
    }


def _nav_item(icon, label, page_id):
    return html.Div(
        [html.Span(icon, style={"fontSize": "15px"}), html.Span(label)],
        id=f"nav-{page_id}",
        n_clicks=0,
        style=_nav_style(active=page_id == "dashboard"),
    )


def _section_label(text):
    return html.Div(
        text,
        style={
            "color": C["dim"],
            "fontSize": "10px",
            "fontWeight": "700",
            "letterSpacing": "0.12em",
            "padding": "20px 16px 6px",
        },
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────

sidebar = html.Div(
    style={
        "position": "fixed",
        "top": 0, "left": 0, "bottom": 0,
        "width": "220px",
        "backgroundColor": C["sidebar"],
        "borderRight": f"1px solid {C['border']}",
        "display": "flex",
        "flexDirection": "column",
        "fontFamily": FONT,
        "zIndex": 1000,
    },
    children=[
        # Logo
        html.Div(
            [
                html.Span("⚡", style={"fontSize": "22px"}),
                html.Div([
                    html.Div("T212 Scanner", style={"color": C["txt"], "fontWeight": "700", "fontSize": "15px", "lineHeight": "1.2"}),
                    html.Div("Practice Mode", style={"color": C["muted"], "fontSize": "11px"}),
                ]),
            ],
            style={
                "display": "flex", "alignItems": "center", "gap": "10px",
                "padding": "24px 16px 20px",
                "borderBottom": f"1px solid {C['border']}",
            },
        ),
        # Nav
        html.Div(
            style={"flex": "1", "overflowY": "auto"},
            children=[
                _section_label("MAIN MENU"),
                _nav_item("📊", "Dashboard",  "dashboard"),
                _nav_item("🔍", "Screener",    "screener"),
                _nav_item("📈", "All Movers", "universe"),
                _nav_item("💼", "Portfolio",  "portfolio"),
                _nav_item("📰", "News",       "news"),
                _nav_item("💱", "Forex",      "forex"),
                _nav_item("🤖", "Auto Trade", "auto"),
                _section_label("ACCOUNT"),
                _nav_item("⚙️", "Settings",  "settings"),
            ],
        ),
        # Status footer
        html.Div(
            [
                html.Div(style={"width": "8px", "height": "8px", "borderRadius": "50%", "backgroundColor": C["green"], "flexShrink": "0"}),
                html.Span("Practice Account", style={"color": C["muted"], "fontSize": "12px"}),
            ],
            style={
                "display": "flex", "alignItems": "center", "gap": "8px",
                "padding": "14px 16px",
                "borderTop": f"1px solid {C['border']}",
            },
        ),
    ],
)

# ── Reusable component builders ───────────────────────────────────────────────

def _metric_row(cash_info: dict):
    free  = float(cash_info.get("free",   0) or 0)
    total = float(cash_info.get("total",  0) or 0)
    pnl   = float(cash_info.get("result", 0) or 0)
    pnl_col = C["green"] if pnl >= 0 else C["red"]
    error = "error" in cash_info

    def card(label, value, color=C["txt"]):
        return dbc.Col(
            html.Div(
                [
                    html.Div(label, style={"color": C["muted"], "fontSize": "11px", "fontWeight": "600", "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "10px"}),
                    html.Div(value, style={"fontSize": "30px", "fontWeight": "700", "letterSpacing": "-0.02em", "color": color}),
                ],
                style=CARD,
            ),
            lg=4, md=6, xs=12,
        )

    if error:
        return dbc.Row([
            card("Cash Available", "—"),
            card("Total Value", "—"),
            card("Today's P&L", "—"),
        ], className="mb-0")

    return dbc.Row([
        card("Cash Available", f"${free:,.2f}"),
        card("Total Value",    f"${total:,.2f}"),
        card("Today's P&L",   f"{pnl:+,.2f}", color=pnl_col),
    ], className="mb-0 g-3")


def _screener_table(rows: list, compact=False, selectable=False, table_id=None):
    kwargs = {}
    _id = table_id or ("screener-table" if selectable else None)
    if _id:
        kwargs["id"] = _id
        kwargs["row_selectable"] = "single"
        kwargs["selected_rows"] = []
    return dash_table.DataTable(
        columns=SCREENER_TABLE_COLS,
        data=[{**r, "Trade?": "BUY"} for r in rows],
        style_table={"overflowX": "auto"},
        style_cell=TBL_CELL,
        style_header=TBL_HDR,
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": C["row_alt"]},
            {"if": {"column_id": "Day Gain%"}, "color": C["green"], "fontWeight": "600"},
            {"if": {"column_id": "Take Profit"}, "color": C["green"]},
            {"if": {"column_id": "Stop Loss"}, "color": C["red"]},
            {
                "if": {"filter_query": '{Trade?} = "BUY"', "column_id": "Trade?"},
                "color": C["green"], "fontWeight": "700",
                "backgroundColor": f"{C['green']}1a",
            },
            {"if": {"state": "selected"}, "backgroundColor": f"{C['green']}18", "border": f"1px solid {C['green']}"},
        ],
        page_size=5 if compact else 10,
        sort_action="native",
        **kwargs,
    )


def _watchlist_table(rows: list):
    check_cond = [
        {
            "if": {"filter_query": f'{{{col}}} = "✗"', "column_id": col},
            "color": C["red"], "fontWeight": "600",
        }
        for col in ("Price OK", "Mkt Cap")
    ] + [
        {
            "if": {"filter_query": f'{{{col}}} = "✓"', "column_id": col},
            "color": C["green"],
        }
        for col in ("Price OK", "Mkt Cap")
    ]
    return dash_table.DataTable(
        columns=WATCHLIST_TABLE_COLS,
        data=rows,
        style_table={"overflowX": "auto"},
        style_cell=TBL_CELL,
        style_header=TBL_HDR,
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": C["row_alt"]},
            {"if": {"column_id": "Day Gain%"}, "color": C["amber"], "fontWeight": "600"},
            {"if": {"column_id": "Missing"}, "color": C["red"], "fontSize": "12px"},
            *check_cond,
        ],
        page_size=10,
        sort_action="native",
    )


def _portfolio_table(positions: list):
    if not positions:
        return html.Div("No open positions.", style={"color": C["muted"], "fontSize": "13px"})
    return dash_table.DataTable(
        data=positions,
        columns=PORTFOLIO_COLS,
        style_table={"overflowX": "auto"},
        style_cell=TBL_CELL,
        style_header=TBL_HDR,
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": C["row_alt"]},
            {"if": {"filter_query": "{ppl} > 0", "column_id": "ppl"}, "color": C["green"]},
            {"if": {"filter_query": "{ppl} < 0", "column_id": "ppl"}, "color": C["red"]},
        ],
        page_size=10,
    )


def _card(title, subtitle, accent, children):
    return html.Div(
        style=CARD,
        children=[
            html.Div(title, style={"color": C["txt"], "fontWeight": "600", "fontSize": "16px"}),
            html.Div(subtitle, style={"color": C["muted"], "fontSize": "12px", "marginTop": "3px", "marginBottom": "16px"}),
            html.Div(
                style={"height": "2px", "backgroundColor": accent, "width": "32px", "borderRadius": "2px", "marginBottom": "16px"},
            ),
            *([children] if not isinstance(children, list) else children),
        ],
    )

# ── Page render functions ─────────────────────────────────────────────────────

def _page_header(title, subtitle):
    return dbc.Row(
        className="mb-4 align-items-center",
        children=[
            dbc.Col([
                html.H3(title, style={"color": C["txt"], "fontWeight": "700", "margin": 0, "letterSpacing": "-0.02em"}),
                html.P(subtitle, style={"color": C["muted"], "fontSize": "13px", "margin": "4px 0 0"}),
            ], width=9),
            dbc.Col(
                html.Div(
                    [
                        html.Div(style={"width": "8px", "height": "8px", "borderRadius": "50%", "backgroundColor": C["green"]}),
                        html.Span("Account Active", style={"color": C["muted"], "fontSize": "13px"}),
                    ],
                    style={"display": "flex", "alignItems": "center", "gap": "8px", "justifyContent": "flex-end"},
                ),
                width=3,
            ),
        ],
    )


def render_dashboard(data):
    passing  = data.get("passing",   [])
    positions = data.get("positions", [])
    cash_info = data.get("cash",      {})

    screener_content = (
        _screener_table(passing[:5], compact=True, table_id="dashboard-table")
        if passing
        else html.Div("No candidates found — market may be closed.", style={"color": C["muted"], "fontSize": "13px"})
    )

    return [
        _page_header("Dashboard", "Monitor top gaining stocks and trading signals."),
        _metric_row(cash_info),
        html.Div(style={"height": "24px"}),
        _card(
            "Top Gainers (preview)",
            "Stocks passing all 5 criteria — showing top 5. Visit Screener for full list.",
            C["green"],
            screener_content,
        ),
        _card(
            "Open Positions",
            "Current holdings in your practice account.",
            C["blue"],
            _portfolio_table(positions),
        ),
    ]


def render_screener(data):
    passing   = data.get("passing",   [])
    watchlist = data.get("watchlist", [])

    passing_content = (
        _screener_table(passing, selectable=True)
        if passing
        else html.Div("No stocks passed all criteria — market may be closed.", style={"color": C["muted"], "fontSize": "13px"})
    )

    watchlist_content = (
        _watchlist_table(watchlist)
        if watchlist
        else html.Div("No watch-list candidates at this time.", style={"color": C["muted"], "fontSize": "13px"})
    )

    hint = html.Div(
        "Click any row to view its intraday chart with VWAP and MACD.",
        style={"color": C["muted"], "fontSize": "12px", "marginBottom": "12px"},
    ) if passing else None

    chart_container = html.Div(
        id="chart-container",
        style={"display": "none"},
        children=[
            html.Div(
                [
                    html.Span(id="chart-title", style={"color": C["txt"], "fontWeight": "600", "fontSize": "16px"}),
                    html.Span(" — Price · VWAP · MACD (5-min intraday)",
                              style={"color": C["muted"], "fontSize": "13px"}),
                ],
                style={"marginBottom": "12px"},
            ),
            dbc.Spinner(
                dcc.Graph(id="stock-chart", config={"displayModeBar": False}),
                color="success",
                spinner_style={"position": "absolute", "top": "50%", "left": "50%"},
            ),
        ],
    )

    return [
        _page_header("Screener", f"Stocks up ≥{MIN_GAIN_PCT:.0f}% on the day and priced ${MIN_PRICE:.0f}–${MAX_PRICE:.0f}."),
        _card(
            "BUY Signals — All Criteria Met",
            f"Top {min(len(passing), 10)} stocks: ≥{MIN_GAIN_PCT:.0f}% gain · price ${MIN_PRICE:.0f}–${MAX_PRICE:.0f}. Click a row for intraday chart.",
            C["green"],
            [hint, passing_content] if hint else [passing_content],
        ),
        html.Div(style={**CARD, "position": "relative"}, children=[chart_container]),
        _card(
            "Watch List — Outside Price Range",
            f"Stocks up ≥{MIN_GAIN_PCT:.0f}% today but outside the ${MIN_PRICE:.0f}–${MAX_PRICE:.0f} price range. Market cap shown as an indicator (✓ >$10M, ✗ under).",
            C["amber"],
            watchlist_content,
        ),
    ]


def render_portfolio(data):
    positions = data.get("positions", [])
    cash_info = data.get("cash",      {})
    return [
        _page_header("Portfolio", "Current open positions in your Trading 212 practice account."),
        _metric_row(cash_info),
        html.Div(style={"height": "24px"}),
        _card(
            "Open Positions",
            f"{len(positions)} position(s) currently open.",
            C["blue"],
            _portfolio_table(positions),
        ),
    ]


def render_news(data):
    passing = data.get("passing", [])
    news    = data.get("news",    {})

    if not passing:
        return [
            _page_header("News", "Latest headlines for screened stocks."),
            html.Div(
                "No screened stocks yet — refresh the data first.",
                style={"color": C["muted"], "fontSize": "13px", "padding": "8px 0"},
            ),
        ]

    divider = {"borderBottom": f"1px solid {C['border']}"}
    items = []
    for i, row in enumerate(passing):
        ticker   = row["Ticker"]
        articles = news.get(ticker, [])
        is_last  = i == len(passing) - 1

        if articles:
            articles_html = html.Ul(
                [
                    html.Li(
                        [
                            html.A(a["title"], href=a["link"], target="_blank",
                                   style={"color": "#7eb8f7", "textDecoration": "none", "fontSize": "13px"}),
                            html.Span(f" · {a['publisher']}" if a.get("publisher") else "",
                                      style={"color": C["muted"], "fontSize": "11px"}),
                        ],
                        style={"marginBottom": "6px"},
                    )
                    for a in articles
                ],
                style={"paddingLeft": "16px", "margin": "8px 0 0"},
            )
        else:
            articles_html = html.Div("No recent news.", style={"color": C["muted"], "fontSize": "12px", "paddingTop": "4px"})

        items.append(
            html.Div(
                [
                    html.Div([
                        html.Span(ticker, style={"color": C["txt"], "fontWeight": "600", "fontSize": "14px"}),
                        html.Span(f"  {row['Day Gain%']}", style={"color": C["green"], "fontWeight": "600", "marginLeft": "8px"}),
                        html.Span(f"  ·  SL {row['Stop Loss']}  →  TP {row['Take Profit']}",
                                  style={"color": C["muted"], "fontSize": "12px"}),
                    ]),
                    articles_html,
                ],
                style={"padding": "16px 4px", **(divider if not is_last else {})},
            )
        )

    return [
        _page_header("News", "Latest headlines for stocks passing the screener."),
        _card("Stock Headlines", f"News for {len(passing)} stock(s).", C["blue"], items),
    ]


def _fmt_vol(v: float) -> str:
    if v >= 1e9: return f"{v/1e9:.1f}B"
    if v >= 1e6: return f"{v/1e6:.1f}M"
    if v >= 1e3: return f"{v/1e3:.0f}K"
    return str(int(v))


def _fmt_cap_short(v: float) -> str:
    if v >= 1e9: return f"${v/1e9:.1f}B"
    if v >= 1e6: return f"${v/1e6:.0f}M"
    return f"${v:,.0f}" if v else "—"


def render_universe(data):
    gainers = data.get("all_gainers", [])

    if not gainers:
        return [
            _page_header("All Movers", "Every stock moving today from Yahoo Finance."),
            html.Div("No data — click Refresh to load.", style={"color": C["muted"], "fontSize": "13px"}),
        ]

    tiles = []
    for g in gainers:
        pct   = g.get("day_gain_pct", 0)
        price = g.get("price", 0)
        cap   = g.get("market_cap", 0)
        vol   = g.get("volume", 0)

        if   pct >= 100: bg, border_col = f"{C['green']}22", C["green"]
        elif pct >= 50:  bg, border_col = f"{C['green']}16", f"{C['green']}88"
        elif pct >= 30:  bg, border_col = f"{C['green']}0d", f"{C['green']}55"
        elif pct >= 0:   bg, border_col = f"{C['amber']}0d", f"{C['amber']}44"
        else:            bg, border_col = f"{C['red']}0d",   f"{C['red']}44"

        pct_color = C["green"] if pct >= 0 else C["red"]

        # Dim tiles that fail the price range criterion
        in_range = 2.0 <= price <= 20.0
        opacity_style = {} if in_range else {"opacity": "0.55"}

        tiles.append(
            dbc.Col(
                html.Div(
                    [
                        # Header row: ticker + gain %
                        html.Div(
                            [
                                html.Span(g["ticker"], style={"fontWeight": "700", "fontSize": "15px", "color": C["txt"]}),
                                html.Span(f"{pct:+.1f}%", style={"fontWeight": "700", "fontSize": "13px", "color": pct_color}),
                            ],
                            style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "4px"},
                        ),
                        # Company name
                        html.Div(
                            g.get("name", ""),
                            style={"color": C["muted"], "fontSize": "11px", "marginBottom": "8px",
                                   "overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"},
                        ),
                        # Price
                        html.Div(
                            f"${price:.2f}",
                            style={"color": C["txt"], "fontWeight": "600", "fontSize": "16px", "marginBottom": "6px"},
                        ),
                        # Volume + cap
                        html.Div(
                            [
                                html.Span(f"Vol {_fmt_vol(vol)}", style={"color": C["muted"], "fontSize": "11px"}),
                                html.Span(f" · {_fmt_cap_short(cap)}", style={"color": C["muted"], "fontSize": "11px"}),
                            ],
                        ),
                        # Price range badge
                        html.Div(
                            "✓ $2–$20" if in_range else "✗ Out of range",
                            style={
                                "marginTop": "8px",
                                "fontSize": "10px",
                                "fontWeight": "600",
                                "color": C["green"] if in_range else C["red"],
                            },
                        ),
                        html.Div("Click to analyse & trade →",
                                 style={"color": C["muted"], "fontSize": "10px", "marginTop": "6px"}),
                    ],
                    id={"type": "tile", "index": g["ticker"]},
                    n_clicks=0,
                    style={
                        "backgroundColor": bg,
                        "border": f"1px solid {border_col}",
                        "borderRadius": "10px",
                        "padding": "14px",
                        "cursor": "pointer",
                        **opacity_style,
                    },
                ),
                xxl=2, xl=2, lg=3, md=4, sm=6, xs=6,
                className="mb-3",
            )
        )

    return [
        _page_header("All Movers", f"{len(gainers)} stocks on the move today — no criteria filter applied."),
        html.Div(
            style=CARD,
            children=[
                html.Div("Day Gainers Universe", style={"color": C["txt"], "fontWeight": "600", "fontSize": "16px"}),
                html.Div(
                    "All stocks from Yahoo Finance top gainers. Dimmed tiles are outside the $2–$20 price range.",
                    style={"color": C["muted"], "fontSize": "12px", "marginTop": "3px", "marginBottom": "16px"},
                ),
                html.Div(style={"height": "2px", "backgroundColor": C["blue"], "width": "32px", "borderRadius": "2px", "marginBottom": "16px"}),
                dbc.Row(tiles, className="g-2"),
            ],
        ),
    ]


def _build_forex_chart(data: dict, label: str) -> go.Figure:
    """3-panel chart: Candlestick+EMA20/50 · RSI · MACD."""
    times = data["times"]
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.55, 0.22, 0.23],
        vertical_spacing=0.04,
        subplot_titles=(f"{label} — Price · EMA20 · EMA50 (1H)", "RSI (14)", "MACD (12, 26, 9)"),
    )
    # Row 1 — Candlestick
    fig.add_trace(go.Candlestick(
        x=times, open=data["open"], high=data["high"], low=data["low"], close=data["close"],
        name="Price",
        increasing_line_color=C["green"],               decreasing_line_color=C["red"],
        increasing_fillcolor=_hex_rgba(C["green"], 0.27), decreasing_fillcolor=_hex_rgba(C["red"], 0.27),
        showlegend=False,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=times, y=data["ema20"], name="EMA 20",
        line={"color": C["green"], "width": 1.5}, mode="lines",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=times, y=data["ema50"], name="EMA 50",
        line={"color": C["amber"], "width": 1.5, "dash": "dot"}, mode="lines",
    ), row=1, col=1)
    # Row 2 — RSI
    fig.add_trace(go.Scatter(
        x=times, y=data["rsi_series"], name="RSI",
        line={"color": C["blue"], "width": 1.5}, mode="lines", showlegend=False,
    ), row=2, col=1)
    for level, col in [(70, C["red"]), (30, C["green"]), (50, C["muted"])]:
        fig.add_hline(y=level, line_dash="dot", line_color=col, opacity=0.45, row=2, col=1)
    # Row 3 — MACD
    hist_colors = [C["green"] if (v or 0) >= 0 else C["red"] for v in data["macd_hist"]]
    fig.add_trace(go.Bar(
        x=times, y=data["macd_hist"], marker_color=hist_colors, opacity=0.55,
        showlegend=False,
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=times, y=data["macd_line"], name="MACD",
        line={"color": C["blue"], "width": 1.5}, mode="lines",
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=times, y=data["macd_signal"], name="Signal",
        line={"color": C["amber"], "width": 1.5}, mode="lines",
    ), row=3, col=1)
    # Layout
    fig.update_layout(
        paper_bgcolor=C["card"], plot_bgcolor=C["card"],
        font={"color": C["txt"], "family": FONT, "size": 12},
        height=540,
        margin={"l": 12, "r": 12, "t": 36, "b": 8},
        legend={"orientation": "h", "y": 1.06, "x": 0.5, "xanchor": "center",
                "bgcolor": "rgba(0,0,0,0)", "font": {"size": 11}},
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        hoverlabel={"bgcolor": C["sidebar"], "font_color": C["txt"], "bordercolor": C["border"]},
        bargap=0.1,
    )
    for row in (1, 2, 3):
        fig.update_xaxes(gridcolor=C["border"], zeroline=False,
                         showline=True, linecolor=C["border"], row=row, col=1)
        fig.update_yaxes(gridcolor=C["border"], zeroline=False,
                         showline=True, linecolor=C["border"], row=row, col=1)
    fig.update_yaxes(range=[20, 80], row=2, col=1)
    for ann in fig.layout.annotations:
        ann.font.color = C["muted"]
        ann.font.size  = 12
    return fig


def _build_forex_modal_body(detail: dict) -> list:
    """6 indicator cards + SL/TP row for the forex modal."""
    entry   = detail["current_price"]
    sl      = detail["stop_loss"]
    tp      = detail["take_profit"]
    sl_pct  = (sl - entry) / entry * 100 if entry else 0
    tp_pct  = (tp - entry) / entry * 100 if entry else 0
    is_jpy  = "JPY" in detail.get("yf", "")
    price_fmt = f"{entry:.3f}" if is_jpy else f"{entry:.5f}"
    atr_str = f"{detail['atr_pips']} pips"

    indicator_row = dbc.Row([
        _indicator_card(
            "RSI (14)", f"{detail['rsi']:.1f}", detail["rsi_bullish"],
            "Momentum oscillator 0–100. Under 30 = oversold (potential bounce). "
            "Over 70 = overbought (potential pullback). "
            "45–70 is the healthy bullish zone — strength without being stretched.",
        ),
        _indicator_card(
            "MACD", "Bullish" if detail["macd_bullish"] else "Bearish",
            detail["macd_bullish"],
            "Compares two moving averages to detect momentum shifts. "
            "When the MACD line crosses above the signal line, buying pressure is building. "
            "Crossing below signals weakening momentum — often an early warning before price drops.",
        ),
        _indicator_card(
            "EMA Trend", "Bullish" if detail["ema_bullish"] else "Bearish",
            detail["ema_bullish"],
            "EMA 20 (fast) vs EMA 50 (slow). When the fast line is above the slow line, "
            "recent price action is outpacing the medium-term trend — bullish. "
            "Below = price is losing ground against its own average.",
        ),
        _indicator_card(
            "24H Change", f"{detail['day_change_pct']:+.3f}%",
            detail["day_change_pct"] >= 0,
            "How much the pair has moved in the last 24 hours. "
            "Strong directional moves (±0.3%+) show conviction behind the move. "
            "Near-zero change = ranging market — harder to trade profitably.",
        ),
        _indicator_card(
            "ATR Volatility", atr_str, detail["atr_pips"] > 0,
            "Average True Range — how many pips this pair typically moves per 1H candle (14-period avg). "
            "Your stop loss is set 1× ATR away, take profit 2× ATR. "
            "A higher ATR means bigger potential profit but also bigger risk per trade.",
        ),
        _indicator_card(
            "Price", price_fmt, True,
            f"Current mid-price for {detail['base']}/{detail['quote']}. "
            "The actual fill price from T212 may differ slightly due to spread — "
            "the difference between the buy (ask) and sell (bid) price.",
        ),
    ], className="g-3 mb-4")

    sl_tp_row = dbc.Row([
        dbc.Col(html.Div([
            html.Div("Stop Loss (−1× ATR)", style={"color": C["muted"], "fontSize": "11px",
                                                    "textTransform": "uppercase", "letterSpacing": "0.06em"}),
            html.Div(f"{sl:.3f}" if is_jpy else f"{sl:.5f}",
                     style={"color": C["red"], "fontWeight": "700", "fontSize": "18px"}),
            html.Div(f"{sl_pct:+.3f}% from entry", style={"color": C["muted"], "fontSize": "11px"}),
        ], style={"backgroundColor": f"{C['red']}0d", "border": f"1px solid {C['red']}33",
                   "borderRadius": "8px", "padding": "12px"}), md=6),
        dbc.Col(html.Div([
            html.Div("Take Profit (+2× ATR · 2:1 R:R)", style={"color": C["muted"], "fontSize": "11px",
                                                                  "textTransform": "uppercase", "letterSpacing": "0.06em"}),
            html.Div(f"{tp:.3f}" if is_jpy else f"{tp:.5f}",
                     style={"color": C["green"], "fontWeight": "700", "fontSize": "18px"}),
            html.Div(f"{tp_pct:+.3f}% from entry", style={"color": C["muted"], "fontSize": "11px"}),
        ], style={"backgroundColor": f"{C['green']}0d", "border": f"1px solid {C['green']}33",
                   "borderRadius": "8px", "padding": "12px"}), md=6),
    ], className="mb-2 g-3")

    return [indicator_row, sl_tp_row]


def render_forex(data):
    import datetime as _dt
    from zoneinfo import ZoneInfo

    forex_pairs = data.get("forex",    [])
    calendar    = data.get("calendar", [])

    if not forex_pairs:
        return [
            _page_header("Forex", "Major currency pairs · 1H analysis · economic calendar."),
            html.Div("Loading forex data — click Refresh to fetch.", style={"color": C["muted"], "fontSize": "13px"}),
        ]

    # ── Session clock ──────────────────────────────────────────────────────────
    now_utc = _dt.datetime.now(ZoneInfo("UTC"))
    hour_utc = now_utc.hour + now_utc.minute / 60.0
    _SESSIONS = {"Tokyo": (0, 9), "London": (8, 17), "New York": (13, 22), "Sydney": (22, 31)}

    def _sess_open(start, end, h):
        return start <= h < end if end <= 24 else h >= start or h < (end - 24)

    session_pills = []
    for name, (start, end) in _SESSIONS.items():
        is_open  = _sess_open(start, end, hour_utc)
        color    = C["green"] if is_open else C["muted"]
        bg       = f"{C['green']}1a" if is_open else "transparent"
        session_pills.append(html.Div([
            html.Div(style={"width": "7px", "height": "7px", "borderRadius": "50%",
                            "backgroundColor": color, "flexShrink": 0}),
            html.Span(name, style={"fontSize": "12px", "fontWeight": "600", "color": color}),
            html.Span(" OPEN" if is_open else " CLOSED", style={"fontSize": "10px", "color": color, "opacity": "0.7"}),
        ], style={"display": "flex", "alignItems": "center", "gap": "6px", "padding": "6px 14px",
                  "borderRadius": "20px", "backgroundColor": bg, "border": f"1px solid {color}55"}))

    session_row = html.Div(
        [html.Span("Sessions:", style={"color": C["muted"], "fontSize": "11px", "fontWeight": "600",
                                        "textTransform": "uppercase", "letterSpacing": "0.08em",
                                        "marginRight": "4px"}),
         *session_pills],
        style={"display": "flex", "alignItems": "center", "flexWrap": "wrap", "gap": "8px",
               "backgroundColor": C["card"], "border": f"1px solid {C['border']}",
               "borderRadius": "12px", "padding": "12px 16px", "marginBottom": "24px"},
    )

    # ── Currency strength bars ─────────────────────────────────────────────────
    strength    = compute_currency_strength(forex_pairs)
    max_abs_score = max((abs(s["score"]) for s in strength), default=1.0) or 1.0

    strength_bars = []
    for item in strength:
        score  = item["score"]
        color  = C["green"] if score > 0.001 else (C["red"] if score < -0.001 else C["muted"])
        width  = int(abs(score) / max_abs_score * 100)
        strength_bars.append(dbc.Col(
            html.Div([
                html.Div([
                    html.Span(item["currency"],
                              style={"color": C["txt"], "fontWeight": "700", "fontSize": "14px"}),
                    html.Span(f"{score:+.3f}%",
                              style={"color": color, "fontSize": "11px", "fontWeight": "600"}),
                ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "5px"}),
                html.Div(style={"height": "5px", "borderRadius": "3px", "backgroundColor": C["border"]},
                         children=[html.Div(style={"width": f"{width}%", "height": "100%",
                                                    "backgroundColor": color, "borderRadius": "3px"})]),
            ], style={"padding": "10px 12px", "backgroundColor": C["row_alt"],
                       "borderRadius": "8px", "border": f"1px solid {C['border']}"}),
            md=3, sm=6, xs=6, className="mb-2",
        ))
    strength_card = _card(
        "Currency Strength Index",
        "Relative 24H performance derived from all 10 major pairs. Green = strengthening, red = weakening.",
        C["blue"], dbc.Row(strength_bars, className="g-2"),
    )

    # ── Pair tiles ─────────────────────────────────────────────────────────────
    tiles = []
    for pair in forex_pairs:
        change   = pair["day_change_pct"]
        rsi      = pair["rsi"]
        is_jpy   = "JPY" in pair["yf"]
        pip_size = 0.01 if is_jpy else 0.0001
        atr_pips = int(pair["atr"] / pip_size) if pair["atr"] and pip_size else 0
        price_str = f"{pair['current_price']:.3f}" if is_jpy else f"{pair['current_price']:.5f}"

        if pair["ema_bullish"] and pair["macd_bullish"]:
            bg, border_col = f"{C['green']}0d", f"{C['green']}55"
        elif not pair["ema_bullish"] and not pair["macd_bullish"]:
            bg, border_col = f"{C['red']}0d",   f"{C['red']}55"
        else:
            bg, border_col = f"{C['amber']}08",  f"{C['amber']}44"

        rsi_note  = " ⚠OB" if rsi > 70 else (" ⚠OS" if rsi < 30 else "")
        rsi_color = C["red"] if rsi > 70 else (C["green"] if rsi < 30 else C["txt"])

        tiles.append(dbc.Col(
            html.Div([
                html.Div([
                    html.Span(pair["label"],
                              style={"fontWeight": "700", "fontSize": "14px", "color": C["txt"]}),
                    html.Span(f"{change:+.3f}%",
                              style={"fontWeight": "700", "fontSize": "12px",
                                     "color": C["green"] if change >= 0 else C["red"]}),
                ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "6px"}),
                html.Div(price_str,
                         style={"color": C["txt"], "fontWeight": "700", "fontSize": "19px",
                                "marginBottom": "8px", "letterSpacing": "-0.02em"}),
                html.Div([
                    html.Span(f"RSI {rsi:.0f}{rsi_note}",
                              style={"color": rsi_color, "fontSize": "11px", "fontWeight": "600"}),
                    html.Span("  ·  ", style={"color": C["border"]}),
                    html.Span("EMA ▲" if pair["ema_bullish"] else "EMA ▼",
                              style={"color": C["green"] if pair["ema_bullish"] else C["red"],
                                     "fontSize": "11px", "fontWeight": "600"}),
                    html.Span("  ·  ", style={"color": C["border"]}),
                    html.Span("MACD ▲" if pair["macd_bullish"] else "MACD ▼",
                              style={"color": C["green"] if pair["macd_bullish"] else C["red"],
                                     "fontSize": "11px", "fontWeight": "600"}),
                ], style={"marginBottom": "5px"}),
                html.Div(f"ATR {atr_pips} pips",
                         style={"color": C["muted"], "fontSize": "10px"}),
                html.Div("Click to analyse & trade →",
                         style={"color": C["muted"], "fontSize": "10px", "marginTop": "6px"}),
            ],
            id={"type": "forex-tile", "index": pair["yf"]},
            n_clicks=0,
            style={"backgroundColor": bg, "border": f"1px solid {border_col}",
                   "borderRadius": "10px", "padding": "14px", "cursor": "pointer"}),
            xxl=2, xl=2, lg=3, md=4, sm=6, xs=6, className="mb-3",
        ))

    pairs_card = html.Div(style=CARD, children=[
        html.Div("Major Pairs", style={"color": C["txt"], "fontWeight": "600", "fontSize": "16px"}),
        html.Div("1H data · EMA20/50 · RSI(14) · MACD(12,26,9) · ATR(14). "
                 "Green border = full bullish alignment · Red = bearish · Amber = mixed.",
                 style={"color": C["muted"], "fontSize": "12px", "marginTop": "3px", "marginBottom": "16px"}),
        html.Div(style={"height": "2px", "backgroundColor": C["green"], "width": "32px",
                         "borderRadius": "2px", "marginBottom": "16px"}),
        dbc.Row(tiles, className="g-2"),
    ])

    # ── Economic calendar ──────────────────────────────────────────────────────
    if calendar:
        now_aware = _dt.datetime.now(_dt.timezone.utc)
        cal_items = []
        for ev in calendar:
            try:
                ev_dt    = _dt.datetime.fromisoformat(ev["date"])
                if ev_dt.tzinfo is None:
                    ev_dt = ev_dt.replace(tzinfo=_dt.timezone.utc)
                ev_et    = ev_dt.astimezone(ZoneInfo("America/New_York"))
                time_str = ev_et.strftime("%a %d %b  %H:%M ET")
                hours    = (ev_dt - now_aware).total_seconds() / 3600
                is_soon  = -0.5 < hours < 24
                is_past  = hours < -0.5
            except Exception:
                time_str, is_soon, is_past = ev.get("date", ""), False, True

            impact_color = C["red"] if ev.get("impact") == "High" else C["amber"]
            currency     = ev.get("country") or ev.get("currency", "")
            actual       = ev.get("actual", "")

            cal_items.append(html.Div([
                html.Div([
                    html.Span(f"● {ev.get('impact', '')}",
                              style={"color": impact_color, "fontSize": "10px", "fontWeight": "700",
                                     "marginRight": "8px"}),
                    html.Span(f"[{currency}]",
                              style={"color": C["muted"], "fontSize": "11px", "fontWeight": "600",
                                     "marginRight": "8px"}),
                    html.Span(ev.get("title", ""),
                              style={"color": C["txt"] if is_soon else C["muted"], "fontSize": "12px",
                                     "fontWeight": "600" if is_soon else "400"}),
                ], style={"display": "flex", "alignItems": "center"}),
                html.Div([
                    html.Span(time_str, style={"color": C["muted"], "fontSize": "11px"}),
                    html.Span(f"  Forecast: {ev.get('forecast') or '—'}",
                              style={"color": C["muted"], "fontSize": "11px"}),
                    html.Span(f"  Prev: {ev.get('previous') or '—'}",
                              style={"color": C["muted"], "fontSize": "11px"}),
                    html.Span(f"  Actual: {actual}" if actual else "",
                              style={"color": C["green"], "fontSize": "11px", "fontWeight": "600"}),
                ]),
            ], style={"padding": "10px 0", "borderBottom": f"1px solid {C['border']}",
                       "opacity": "0.45" if is_past else "1"}))

        cal_content = html.Div(cal_items)
    else:
        cal_content = html.Div("Economic calendar unavailable — check internet connection.",
                                style={"color": C["muted"], "fontSize": "13px"})

    calendar_card = _card(
        "Economic Calendar",
        "High & Medium impact events this week · ● Red = High impact · ● Amber = Medium · Times in ET",
        C["amber"], cal_content,
    )

    return [
        _page_header("Forex", "Major pairs · 1H analysis · live economic calendar · no PDT rule."),
        session_row,
        strength_card,
        pairs_card,
        calendar_card,
    ]


def render_autotrader(state: dict):
    running    = state.get("running",              False)
    mkt_open   = state.get("market_open",          False)
    daily_pnl  = state.get("daily_realized_pnl",   0.0)
    target_hit = state.get("daily_target_hit",     False)
    loss_hit   = state.get("daily_loss_limit_hit", False)
    signals    = state.get("pending_signals",      {})
    open_trd   = state.get("open_trades",          {})
    trade_log  = state.get("trade_log",            [])
    last_scan  = state.get("last_scan_at",         "—")
    last_mon   = state.get("last_monitor_at",      "—")
    last_err   = state.get("last_error",           "")

    # ── Status cards ──────────────────────────────────────────────────────────
    def _status_card(label, value, color):
        return dbc.Col(
            html.Div([
                html.Div(label, style={"color": C["muted"], "fontSize": "11px", "fontWeight": "600",
                                        "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "10px"}),
                html.Div(value, style={"fontSize": "20px", "fontWeight": "700", "color": color}),
            ], style=CARD),
            lg=3, md=6, xs=12,
        )

    if loss_hit:
        guard_val, guard_col = f"Loss Limit Hit (−${DAILY_LOSS_LIMIT:.0f})", C["red"]
    elif target_hit:
        guard_val, guard_col = f"Target Hit (+${DAILY_TARGET:.0f})", C["green"]
    else:
        guard_val, guard_col = "Active", C["green"]

    status_row = dbc.Row([
        _status_card("Engine",      "Running ●" if running else "Stopped ○",
                     C["green"] if running else C["red"]),
        _status_card("Market",      "Open (9:45–15:30 ET)" if mkt_open else "Closed",
                     C["green"] if mkt_open else C["muted"]),
        _status_card("Daily P&L",   f"${daily_pnl:+.2f}",
                     C["green"] if daily_pnl >= 0 else C["red"]),
        _status_card("Guard",       guard_val, guard_col),
    ], className="mb-0 g-3")

    # ── Pending signals ───────────────────────────────────────────────────────
    if signals:
        signal_cards = []
        for ticker, sig in signals.items():
            entry  = sig["entry_price"]
            sl     = sig["stop_loss"]
            tp     = sig["take_profit"]
            sl_pct = (sl - entry) / entry * 100 if entry else 0
            tp_pct = (tp - entry) / entry * 100 if entry else 0
            signal_cards.append(
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            html.Span(ticker, style={"color": C["txt"], "fontWeight": "700", "fontSize": "15px"}),
                            html.Span(f"  +{sig['day_gain_pct']:.1f}%",
                                      style={"color": C["green"], "fontWeight": "600", "marginLeft": "8px"}),
                            html.Span(f"  ·  ${entry:.2f}  ·  Vol {sig['rel_volume']:.1f}x",
                                      style={"color": C["muted"], "fontSize": "12px"}),
                        ], md=6),
                        dbc.Col([
                            html.Span(f"SL ${sl:.2f} ({sl_pct:+.1f}%)",
                                      style={"color": C["red"], "fontSize": "12px", "fontWeight": "600"}),
                            html.Span("  →  ", style={"color": C["muted"]}),
                            html.Span(f"TP ${tp:.2f} ({tp_pct:+.1f}%)",
                                      style={"color": C["green"], "fontSize": "12px", "fontWeight": "600"}),
                        ], md=4),
                        dbc.Col([
                            html.Div(f"{sig['suggested_qty']} shares · risk ${sig['risk_usd']:.2f}",
                                     style={"color": C["muted"], "fontSize": "11px", "marginBottom": "6px"}),
                            dbc.Row([
                                dbc.Col(dbc.Button(
                                    "✓ Confirm",
                                    id={"type": "confirm-signal", "index": ticker},
                                    n_clicks=0,
                                    size="sm",
                                    style={"backgroundColor": C["green"], "color": "#000", "border": "none",
                                           "borderRadius": "6px", "fontWeight": "700", "fontSize": "12px",
                                           "width": "100%", "fontFamily": FONT},
                                ), xs=6),
                                dbc.Col(dbc.Button(
                                    "✗ Dismiss",
                                    id={"type": "dismiss-signal", "index": ticker},
                                    n_clicks=0,
                                    size="sm",
                                    style={"backgroundColor": C["row_alt"], "color": C["muted"],
                                           "border": f"1px solid {C['border']}", "borderRadius": "6px",
                                           "fontWeight": "600", "fontSize": "12px",
                                           "width": "100%", "fontFamily": FONT},
                                ), xs=6),
                            ], className="g-2"),
                        ], md=2),
                    ], align="center"),
                ], style={
                    "backgroundColor": f"{C['green']}08",
                    "border": f"1px solid {C['green']}33",
                    "borderRadius": "10px",
                    "padding": "14px 16px",
                    "marginBottom": "10px",
                })
            )
        signals_content = signal_cards
    else:
        msg = "Waiting for market hours and scan…" if running else "Start engine to begin scanning."
        signals_content = html.Div(msg, style={"color": C["muted"], "fontSize": "13px"})

    # ── Open trades ───────────────────────────────────────────────────────────
    open_rows = [
        {
            "Ticker":       ticker,
            "Entry":        f"${t['entry_price']:.2f}",
            "SL":           f"${t['stop_loss']:.2f}",
            "TP":           f"${t['take_profit']:.2f}",
            "Qty":          t["quantity"],
            "Confirmed":    t.get("confirmed_at", "—"),
        }
        for ticker, t in open_trd.items()
    ]
    open_tbl_content = dash_table.DataTable(
        columns=[
            {"name": "Ticker",    "id": "Ticker"},
            {"name": "Entry",     "id": "Entry"},
            {"name": "SL",        "id": "SL"},
            {"name": "TP",        "id": "TP"},
            {"name": "Qty",       "id": "Qty"},
            {"name": "Confirmed", "id": "Confirmed"},
        ],
        data=open_rows,
        style_table={"overflowX": "auto"},
        style_cell=TBL_CELL,
        style_header=TBL_HDR,
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": C["row_alt"]},
            {"if": {"column_id": "TP"}, "color": C["green"]},
            {"if": {"column_id": "SL"}, "color": C["red"]},
        ],
        page_size=10,
    ) if open_rows else html.Div("No open trades.", style={"color": C["muted"], "fontSize": "13px"})

    # ── Trade log ─────────────────────────────────────────────────────────────
    wins    = [t for t in trade_log if t["pnl"] > 0]
    total   = len(trade_log)
    win_pct = len(wins) / total * 100 if total else 0
    net_pnl = sum(t["pnl"] for t in trade_log)

    log_summary = html.Div([
        html.Span(f"{total} trade{'s' if total != 1 else ''}", style={"color": C["txt"], "fontWeight": "600"}),
        html.Span(f"  ·  Win rate {win_pct:.0f}%", style={"color": C["muted"]}),
        html.Span(f"  ·  Net {net_pnl:+.2f}", style={"color": C["green"] if net_pnl >= 0 else C["red"], "fontWeight": "600"}),
    ], style={"fontSize": "13px", "marginBottom": "12px"}) if total else None

    log_content = dash_table.DataTable(
        columns=[
            {"name": "Ticker",  "id": "ticker"},
            {"name": "Entry",   "id": "entry_price"},
            {"name": "Exit",    "id": "exit_price"},
            {"name": "Qty",     "id": "quantity"},
            {"name": "P&L",     "id": "pnl"},
            {"name": "Reason",  "id": "exit_reason"},
            {"name": "Time",    "id": "closed_at"},
        ],
        data=trade_log,
        style_table={"overflowX": "auto"},
        style_cell=TBL_CELL,
        style_header=TBL_HDR,
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": C["row_alt"]},
            {"if": {"filter_query": "{pnl} > 0", "column_id": "pnl"}, "color": C["green"], "fontWeight": "600"},
            {"if": {"filter_query": "{pnl} < 0", "column_id": "pnl"}, "color": C["red"],   "fontWeight": "600"},
            {"if": {"filter_query": '{exit_reason} = "TP"', "column_id": "exit_reason"}, "color": C["green"]},
            {"if": {"filter_query": '{exit_reason} = "SL"', "column_id": "exit_reason"}, "color": C["red"]},
        ],
        page_size=20,
        sort_action="native",
    ) if trade_log else html.Div("No trades completed today.", style={"color": C["muted"], "fontSize": "13px"})

    # ── Footer: scan timing + last error ─────────────────────────────────────
    footer_items = [
        html.Span(f"Last scan {last_scan}  ·  Last exit check {last_mon}",
                  style={"color": C["muted"], "fontSize": "11px"}),
    ]
    if last_err:
        footer_items.append(
            html.Div(f"⚠ {last_err[:120]}", style={"color": C["amber"], "fontSize": "11px", "marginTop": "4px"})
        )

    return [
        _page_header("Auto Trade",
                     f"Semi-automatic engine · 1% risk/trade · target ${DAILY_TARGET:.0f}/day · stop −${DAILY_LOSS_LIMIT:.0f}"),
        status_row,
        html.Div(style={"height": "24px"}),
        _card("Pending Signals",
              f"All 6 indicators green · {len(signals)} waiting for confirmation",
              C["green"], signals_content),
        _card("Open Trades",
              f"{len(open_trd)} position(s) being monitored · auto-exit at SL/TP",
              C["blue"], open_tbl_content),
        _card("Today's Trade Log",
              "Completed trades this session",
              C["amber"], [log_summary, log_content] if log_summary else [log_content]),
        html.Div(footer_items, style={"textAlign": "right", "marginTop": "-12px", "marginBottom": "24px"}),
    ]


def render_settings(data):
    cash_info = data.get("cash", {})
    rows = [
        ("API Mode",        "Practice (Demo)"),
        ("T212 Base URL",   "demo.trading212.com"),
        ("Criteria 1",       f"≥{MIN_GAIN_PCT:.0f}% day gain"),
        ("Criteria 2",       f"Price ${MIN_PRICE:.0f} – ${MAX_PRICE:.0f}"),
        ("Indicators",       f"Market cap (>{MIN_MARKET_CAP/1e6:.0f}M) · Rel Volume · VWAP · MACD"),
        ("Auto Refresh",    "Every 5 minutes"),
        ("Stop / Take",     "2 : 1 reward-to-risk ratio"),
    ]
    table_rows = [
        html.Tr([
            html.Td(k, style={"color": C["muted"], "padding": "10px 0", "fontSize": "13px", "width": "220px"}),
            html.Td(v, style={"color": C["txt"],   "padding": "10px 0", "fontSize": "13px", "fontWeight": "500"}),
        ])
        for k, v in rows
    ]
    return [
        _page_header("Settings", "Current configuration for the T212 Scanner."),
        _card(
            "Configuration",
            "These values are loaded from your .env file.",
            C["blue"],
            html.Table(
                table_rows,
                style={"borderCollapse": "collapse", "width": "100%"},
            ),
        ),
    ]


# ── App layout ────────────────────────────────────────────────────────────────

app.layout = html.Div(
    style={"backgroundColor": C["bg"], "fontFamily": FONT, "minHeight": "100vh"},
    children=[
        dcc.Store(id="active-page",    data="dashboard"),
        dcc.Store(id="app-data",       data={}),
        dcc.Store(id="selected-stock", data=None),
        dcc.Store(id="modal-detail",   data=None),
        dcc.Store(id="trader-state",      data={}),
        dcc.Store(id="selected-forex",    data=None),
        dcc.Store(id="forex-modal-detail", data=None),
        dcc.Interval(id="auto-refresh",  interval=5 * 60 * 1000, n_intervals=0),
        dcc.Interval(id="chart-refresh", interval=5 * 60 * 1000, n_intervals=0),
        dcc.Interval(id="trader-poll",   interval=60_000,         n_intervals=0),

        # ── Stock detail modal (fixed structure — always in DOM) ──────────
        dbc.Modal(
            id="stock-modal",
            size="xl",
            scrollable=True,
            centered=True,
            is_open=False,
            children=[
                dbc.ModalHeader(
                    dbc.ModalTitle(id="modal-title",
                                   style={"color": C["txt"], "fontFamily": FONT, "fontWeight": "700"}),
                    close_button=True,
                    style={"backgroundColor": C["sidebar"],
                           "borderBottom": f"1px solid {C['border']}"},
                ),
                dbc.ModalBody(
                    style={"backgroundColor": C["card"], "padding": "24px"},
                    children=[
                        # Dynamic: indicator cards + SL/TP boxes
                        dbc.Spinner(html.Div(id="modal-body"), color="success", type="border"),

                        # Fixed: chart panel (shown after first load)
                        html.Div(
                            id="modal-chart-section",
                            style={"display": "none"},
                            children=[
                                dcc.Graph(id="modal-chart",
                                          config={"displayModeBar": False},
                                          style={"marginBottom": "4px"}),
                                html.Div(id="modal-chart-ts",
                                         style={"textAlign": "right", "color": C["muted"],
                                                "fontSize": "11px", "marginBottom": "20px"}),
                            ],
                        ),

                        # Fixed: trade form (shown after first load)
                        html.Div(
                            id="modal-trade-section",
                            style={"display": "none"},
                            children=[
                                html.Div(style={"height": "1px", "backgroundColor": C["border"], "marginBottom": "20px"}),
                                html.Div("Place Trade",
                                         style={"color": C["txt"], "fontWeight": "700",
                                                "fontSize": "16px", "marginBottom": "16px"}),
                                dbc.Row([
                                    dbc.Col([
                                        html.Label("Quantity (shares)",
                                                   style={"color": C["muted"], "fontSize": "12px",
                                                          "fontWeight": "600", "marginBottom": "6px",
                                                          "display": "block"}),
                                        dbc.Input(
                                            id="modal-quantity",
                                            type="number",
                                            value=1,
                                            min=0.01,
                                            step=0.01,
                                            debounce=True,
                                            style={"backgroundColor": C["card"], "color": C["txt"],
                                                   "border": f"1px solid {C['border']}",
                                                   "borderRadius": "8px", "fontFamily": FONT},
                                        ),
                                    ], md=4),
                                    dbc.Col(html.Div(id="modal-pnl",
                                                     style={"paddingTop": "4px"}), md=8),
                                ], className="mb-4 g-3"),
                                dbc.Row([
                                    dbc.Col(dbc.Button(
                                        "▲  BUY", id="modal-buy-btn", n_clicks=0,
                                        style={"backgroundColor": C["green"], "color": "#000",
                                               "border": "none", "borderRadius": "8px",
                                               "fontWeight": "700", "fontSize": "14px",
                                               "padding": "10px 28px", "fontFamily": FONT,
                                               "width": "100%"},
                                    ), md=3),
                                    dbc.Col(dbc.Button(
                                        "▼  SELL", id="modal-sell-btn", n_clicks=0,
                                        style={"backgroundColor": C["red"], "color": "#fff",
                                               "border": "none", "borderRadius": "8px",
                                               "fontWeight": "700", "fontSize": "14px",
                                               "padding": "10px 28px", "fontFamily": FONT,
                                               "width": "100%"},
                                    ), md=3),
                                    dbc.Col(html.Div(id="modal-trade-result",
                                                     style={"paddingTop": "8px", "fontSize": "13px",
                                                            "fontWeight": "600"}), md=6),
                                ], className="g-3"),
                            ],
                        ),
                    ],
                ),
            ],
        ),

        # ── Forex detail modal ───────────────────────────────────────────────
        dbc.Modal(
            id="forex-modal",
            size="xl",
            scrollable=True,
            centered=True,
            is_open=False,
            children=[
                dbc.ModalHeader(
                    dbc.ModalTitle(id="forex-modal-title",
                                   style={"color": C["txt"], "fontFamily": FONT, "fontWeight": "700"}),
                    close_button=True,
                    style={"backgroundColor": C["sidebar"], "borderBottom": f"1px solid {C['border']}"},
                ),
                dbc.ModalBody(
                    style={"backgroundColor": C["card"], "padding": "24px"},
                    children=[
                        dbc.Spinner(html.Div(id="forex-modal-body"), color="success", type="border"),
                        html.Div(
                            id="forex-modal-chart-section",
                            style={"display": "none"},
                            children=[
                                dcc.Graph(id="forex-modal-chart",
                                          config={"displayModeBar": False},
                                          style={"marginBottom": "4px"}),
                                html.Div(id="forex-modal-chart-ts",
                                         style={"textAlign": "right", "color": C["muted"],
                                                "fontSize": "11px", "marginBottom": "20px"}),
                            ],
                        ),
                        html.Div(
                            id="forex-modal-trade-section",
                            style={"display": "none"},
                            children=[
                                html.Div(style={"height": "1px", "backgroundColor": C["border"], "marginBottom": "20px"}),
                                html.Div([
                                    html.Span("Place Trade",
                                              style={"color": C["txt"], "fontWeight": "700", "fontSize": "16px"}),
                                    html.Span(" via OANDA",
                                              style={"color": C["blue"], "fontWeight": "600", "fontSize": "13px",
                                                     "marginLeft": "6px"}),
                                    html.Span(id="oanda-balance-badge", style={"marginLeft": "10px"}),
                                ], style={"marginBottom": "16px", "display": "flex", "alignItems": "center"}),
                                dbc.Row([
                                    dbc.Col([
                                        html.Label("Quantity (units)",
                                                   style={"color": C["muted"], "fontSize": "12px",
                                                          "fontWeight": "600", "marginBottom": "6px",
                                                          "display": "block"}),
                                        dbc.Input(
                                            id="forex-modal-quantity",
                                            type="number",
                                            value=10000,
                                            min=100,
                                            step=1000,
                                            debounce=True,
                                            style={"backgroundColor": C["card"], "color": C["txt"],
                                                   "border": f"1px solid {C['border']}",
                                                   "borderRadius": "8px", "fontFamily": FONT},
                                        ),
                                        html.Div("1 mini lot = 10,000 units",
                                                 style={"color": C["muted"], "fontSize": "10px", "marginTop": "4px"}),
                                    ], md=4),
                                    dbc.Col(html.Div(id="forex-modal-pnl", style={"paddingTop": "4px"}), md=8),
                                ], className="mb-4 g-3"),
                                dbc.Row([
                                    dbc.Col(dbc.Button(
                                        "▲  BUY", id="forex-modal-buy-btn", n_clicks=0,
                                        style={"backgroundColor": C["green"], "color": "#000",
                                               "border": "none", "borderRadius": "8px",
                                               "fontWeight": "700", "fontSize": "14px",
                                               "padding": "10px 28px", "fontFamily": FONT, "width": "100%"},
                                    ), md=3),
                                    dbc.Col(dbc.Button(
                                        "▼  SELL", id="forex-modal-sell-btn", n_clicks=0,
                                        style={"backgroundColor": C["red"], "color": "#fff",
                                               "border": "none", "borderRadius": "8px",
                                               "fontWeight": "700", "fontSize": "14px",
                                               "padding": "10px 28px", "fontFamily": FONT, "width": "100%"},
                                    ), md=3),
                                    dbc.Col(html.Div(id="forex-modal-trade-result",
                                                     style={"paddingTop": "8px", "fontSize": "13px",
                                                            "fontWeight": "600"}), md=6),
                                ], className="g-3"),
                            ],
                        ),
                    ],
                ),
            ],
        ),

        sidebar,

        # Top refresh bar (always visible)
        html.Div(
            style={
                "position": "fixed", "top": 0, "right": 0,
                "left": "220px",
                "backgroundColor": C["bg"],
                "borderBottom": f"1px solid {C['border']}",
                "padding": "12px 36px",
                "display": "flex", "alignItems": "center", "justifyContent": "flex-end",
                "gap": "12px", "zIndex": 999,
            },
            children=[
                html.Div(id="last-updated", style={"color": C["muted"], "fontSize": "12px"}),
                dbc.Spinner(html.Span(id="spinner-target"), size="sm", color="success",
                            spinner_style={"verticalAlign": "middle"}),
                dbc.Button(
                    "↻  Refresh",
                    id="refresh-btn",
                    n_clicks=0,
                    style={
                        "backgroundColor": C["green"], "color": "#000",
                        "border": "none", "borderRadius": "8px",
                        "fontWeight": "600", "fontSize": "13px",
                        "padding": "7px 18px", "fontFamily": FONT,
                    },
                ),
            ],
        ),

        # Main content area (padded for top bar)
        html.Div(
            id="main-content",
            style={"marginLeft": "220px", "padding": "72px 36px 36px"},
        ),
    ],
)

# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("active-page", "data"),
    [Input(f"nav-{p}", "n_clicks") for p in PAGES],
    prevent_initial_call=True,
)
def set_active_page(*_):
    if not ctx.triggered_id:
        return "dashboard"
    return ctx.triggered_id.replace("nav-", "")


@callback(
    *[Output(f"nav-{p}", "style") for p in PAGES],
    Input("active-page", "data"),
)
def update_nav_styles(active_page):
    return [_nav_style(active=p == active_page) for p in PAGES]


@callback(
    Output("app-data",       "data"),
    Output("spinner-target", "children"),
    Output("last-updated",   "children"),
    Input("refresh-btn",  "n_clicks"),
    Input("auto-refresh", "n_intervals"),
)
def fetch_data(n_clicks, n_intervals):
    import datetime
    cash_info  = t212.get_account_info()
    positions  = t212.get_portfolio()
    df_pass, df_watch = screen_stocks()
    all_gainers = get_all_gainers()
    forex_data  = get_forex_overview()
    calendar    = get_economic_calendar()

    passing_records   = df_pass.to_dict("records")  if not df_pass.empty  else []
    watchlist_records = df_watch.to_dict("records") if not df_watch.empty else []

    news = {row["Ticker"]: get_news(row["Ticker"]) for row in passing_records}

    now = datetime.datetime.now().strftime("%H:%M:%S")
    return (
        {
            "cash":        cash_info,
            "positions":   positions,
            "passing":     passing_records,
            "watchlist":   watchlist_records,
            "news":        news,
            "all_gainers": all_gainers,
            "forex":       forex_data,
            "calendar":    calendar,
        },
        "",
        f"Last updated {now}",
    )


@callback(
    Output("main-content", "children"),
    Input("active-page", "data"),
    Input("app-data",    "data"),
)
def render_page(active_page, data):
    if not data:
        return html.Div(
            [
                dbc.Spinner(color="success"),
                html.Span(" Loading data…", style={"color": C["muted"], "marginLeft": "12px", "fontSize": "14px"}),
            ],
            style={"display": "flex", "alignItems": "center", "padding": "60px 0"},
        )

    if active_page == "auto":
        raise PreventUpdate  # handled by render_auto_page_from_state

    renderers = {
        "dashboard": render_dashboard,
        "screener":  render_screener,
        "universe":  render_universe,
        "portfolio": render_portfolio,
        "news":      render_news,
        "forex":     render_forex,
        "settings":  render_settings,
    }
    return renderers.get(active_page, render_dashboard)(data)


# ── Stock-selection callbacks ─────────────────────────────────────────────────

@callback(
    Output("selected-stock", "data"),
    Input({"type": "tile", "index": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def set_selected_from_tile(tile_clicks):
    if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
        raise PreventUpdate
    if not any(v for v in tile_clicks if v):
        raise PreventUpdate
    return ctx.triggered_id["index"]


@callback(
    Output("selected-stock", "data", allow_duplicate=True),
    Input("dashboard-table", "selected_rows"),
    State("dashboard-table", "data"),
    prevent_initial_call=True,
)
def set_selected_from_dashboard(selected_rows, table_data):
    if not selected_rows or not table_data:
        raise PreventUpdate
    return table_data[selected_rows[0]]["Ticker"]


@callback(
    Output("stock-modal", "is_open"),
    Input("selected-stock", "data"),
    prevent_initial_call=True,
)
def toggle_modal(ticker):
    return bool(ticker)


_CHART_HIDDEN = {"display": "none"}
_CHART_SHOWN  = {"display": "block"}
_TRADE_HIDDEN = {"display": "none"}
_TRADE_SHOWN  = {
    "backgroundColor": C["row_alt"],
    "border": f"1px solid {C['border']}",
    "borderRadius": "12px",
    "padding": "20px",
    "marginTop": "4px",
}


@callback(
    Output("modal-title",         "children"),
    Output("modal-body",          "children"),
    Output("modal-chart",         "figure"),
    Output("modal-chart-section", "style"),
    Output("modal-chart-ts",      "children"),
    Output("modal-trade-section", "style"),
    Output("modal-detail",        "data"),
    Input("selected-stock", "data"),
    prevent_initial_call=True,
)
def populate_modal(ticker):
    import datetime
    _blank = go.Figure()
    _blank.update_layout(paper_bgcolor=C["card"], plot_bgcolor=C["card"], height=100)

    if not ticker:
        raise PreventUpdate
    try:
        detail     = get_stock_detail(ticker)
        chart_data = get_chart_data(ticker) if not detail.get("error") else None

        if detail.get("error"):
            body = html.Div([
                html.P("⚠  No intraday data available for this stock.",
                       style={"color": C["amber"], "fontWeight": "600", "marginBottom": "8px"}),
                html.P("Market may be closed, the stock halted, or yfinance has no data yet.",
                       style={"color": C["muted"], "fontSize": "13px"}),
            ], style={"padding": "20px 0"})
            return ticker, body, _blank, _CHART_HIDDEN, "", _TRADE_HIDDEN, None

        fig  = _build_chart(chart_data, ticker) if chart_data else _blank
        ts   = datetime.datetime.now().strftime("Updated %H:%M:%S · refreshes every 5 min")
        body = _build_modal_indicators(detail)

        return (
            ticker,
            body,
            fig,
            _CHART_SHOWN,
            ts,
            _TRADE_SHOWN,
            detail,          # stored for P&L callback and refresh
        )
    except Exception as exc:
        body = html.Div([
            html.P(f"⚠  Error loading {ticker}",
                   style={"color": C["red"], "fontWeight": "600", "marginBottom": "8px"}),
            html.P(str(exc)[:200],
                   style={"color": C["muted"], "fontSize": "12px", "fontFamily": "monospace"}),
        ], style={"padding": "20px 0"})
        return ticker, body, _blank, _CHART_HIDDEN, "", _TRADE_HIDDEN, None


@callback(
    Output("modal-chart",    "figure",   allow_duplicate=True),
    Output("modal-chart-ts", "children", allow_duplicate=True),
    Input("chart-refresh", "n_intervals"),
    State("selected-stock", "data"),
    State("stock-modal",    "is_open"),
    prevent_initial_call=True,
)
def refresh_modal_chart(_, ticker, is_open):
    import datetime
    if not is_open or not ticker:
        raise PreventUpdate
    try:
        chart_data = get_chart_data(ticker)
        if not chart_data:
            raise PreventUpdate
        fig = _build_chart(chart_data, ticker)
        ts  = datetime.datetime.now().strftime("Updated %H:%M:%S · refreshes every 5 min")
        return fig, ts
    except Exception:
        raise PreventUpdate


@callback(
    Output("selected-stock", "data", allow_duplicate=True),
    Input("stock-modal", "is_open"),
    prevent_initial_call=True,
)
def clear_on_close(is_open):
    if not is_open:
        return None
    raise PreventUpdate


@callback(
    Output("modal-trade-result", "children"),
    Input("modal-buy-btn",  "n_clicks"),
    Input("modal-sell-btn", "n_clicks"),
    State("modal-quantity",    "value"),
    State("selected-stock",    "data"),
    prevent_initial_call=True,
)
def place_trade(buy_clicks, sell_clicks, quantity, ticker):
    if not ctx.triggered_id or not ticker or not quantity:
        raise PreventUpdate
    side = "BUY" if ctx.triggered_id == "modal-buy-btn" else "SELL"
    qty  = abs(float(quantity)) * (1 if side == "BUY" else -1)

    t212_ticker = t212.find_ticker(ticker)
    if not t212_ticker:
        return html.Span(f"✗  {ticker} not found on T212", style={"color": C["red"]})

    result = t212.place_market_order(t212_ticker, qty)
    if "error" in result:
        short_err = result["error"][:80]
        return html.Span(f"✗  {short_err}", style={"color": C["red"]})

    order_id = result.get("id", "—")
    return html.Span(
        f"✓  {side} {abs(qty):.2f} × {ticker} — Order #{order_id}",
        style={"color": C["green"]},
    )


@callback(
    Output("modal-pnl", "children"),
    Input("modal-quantity", "value"),
    State("modal-detail",   "data"),
    prevent_initial_call=True,
)
def update_pnl(quantity, detail):
    if not quantity or not detail:
        raise PreventUpdate
    q     = float(quantity)
    entry = detail.get("current_price", 0)
    sl    = detail.get("stop_loss",     0)
    tp    = detail.get("take_profit",   0)
    cost   = q * entry
    profit = q * (tp - entry)
    loss   = q * (entry - sl)

    return html.Div([
        html.Div(
            f"{q:g} share{'s' if q != 1 else ''} × ${entry:.2f} = ${cost:,.2f}",
            style={"color": C["txt"], "fontWeight": "600", "fontSize": "14px", "marginBottom": "8px"},
        ),
        dbc.Row([
            dbc.Col(html.Div([
                html.Div("Profit at TP", style={"color": C["muted"], "fontSize": "11px",
                                                 "textTransform": "uppercase", "letterSpacing": "0.06em"}),
                html.Div(f"+${profit:,.2f}", style={"color": C["green"], "fontWeight": "700",
                                                      "fontSize": "18px"}),
            ], style={"backgroundColor": f"{C['green']}0d",
                       "border": f"1px solid {C['green']}33",
                       "borderRadius": "8px", "padding": "10px 14px"}), md=6),
            dbc.Col(html.Div([
                html.Div("Risk at SL", style={"color": C["muted"], "fontSize": "11px",
                                               "textTransform": "uppercase", "letterSpacing": "0.06em"}),
                html.Div(f"-${loss:,.2f}", style={"color": C["red"], "fontWeight": "700",
                                                    "fontSize": "18px"}),
            ], style={"backgroundColor": f"{C['red']}0d",
                       "border": f"1px solid {C['red']}33",
                       "borderRadius": "8px", "padding": "10px 14px"}), md=6),
        ], className="g-2"),
    ])


# ── Modal helpers ─────────────────────────────────────────────────────────────

def _indicator_card(label: str, value: str, passed: bool, note: str = ""):
    color = C["green"] if passed else C["red"]
    return dbc.Col(
        html.Div(
            [
                html.Div(label, style={"color": C["muted"], "fontSize": "10px", "fontWeight": "700",
                                        "textTransform": "uppercase", "letterSpacing": "0.08em", "marginBottom": "8px"}),
                html.Div(value, style={"color": C["txt"], "fontSize": "20px", "fontWeight": "700",
                                        "letterSpacing": "-0.02em", "marginBottom": "6px"}),
                html.Div(
                    [
                        html.Span("✓ " if passed else "✗ ", style={"fontWeight": "900"}),
                        html.Span("PASS" if passed else "FAIL"),
                    ],
                    style={"color": color, "fontSize": "12px", "fontWeight": "700"},
                ),
                html.Div(note, style={"color": C["muted"], "fontSize": "11px", "marginTop": "4px"}) if note else None,
            ],
            style={
                "backgroundColor": f"{color}12",
                "border": f"1px solid {color}44",
                "borderRadius": "10px",
                "padding": "16px",
            },
        ),
        md=4, sm=6, xs=12,
        className="mb-3",
    )


def _build_modal_indicators(detail: dict) -> list:
    """Returns indicator cards + SL/TP row for modal-body (chart & trade form are fixed layout)."""
    entry  = detail["current_price"]
    sl     = detail["stop_loss"]
    tp     = detail["take_profit"]
    sl_pct = (sl - entry) / entry * 100 if entry else 0
    tp_pct = (tp - entry) / entry * 100 if entry else 0

    indicator_row = dbc.Row([
        _indicator_card("Day Gain",   f"{detail['day_gain_pct']:+.1f}%",
                        detail["gain_ok"],    f"Threshold ≥{MIN_GAIN_PCT:.0f}%"),
        _indicator_card("Price",      f"${entry:.2f}",
                        detail["price_ok"],   f"Range ${MIN_PRICE:.0f}–${MAX_PRICE:.0f}"),
        _indicator_card("Market Cap", _fmt_cap(detail["market_cap"]),
                        detail["cap_ok"],     f"Threshold >${MIN_MARKET_CAP/1e6:.0f}M"),
        _indicator_card("VWAP",       "Above" if detail["vwap_bullish"] else "Below",
                        detail["vwap_bullish"], "Price vs VWAP"),
        _indicator_card("MACD",       "Bullish" if detail["macd_bullish"] else "Bearish",
                        detail["macd_bullish"], "MACD vs Signal"),
        _indicator_card("Rel Volume", f"{detail['rel_volume']:.1f}x",
                        detail["vol_high"],   "vs 20-day avg"),
    ], className="g-3 mb-4")

    sl_tp_row = dbc.Row([
        dbc.Col(html.Div([
            html.Div("Stop Loss", style={"color": C["muted"], "fontSize": "11px",
                                          "textTransform": "uppercase", "letterSpacing": "0.06em"}),
            html.Div(f"${sl:.2f}", style={"color": C["red"], "fontWeight": "700", "fontSize": "18px"}),
            html.Div(f"{sl_pct:+.1f}% from entry", style={"color": C["muted"], "fontSize": "11px"}),
        ], style={"backgroundColor": f"{C['red']}0d", "border": f"1px solid {C['red']}33",
                   "borderRadius": "8px", "padding": "12px"}), md=6),
        dbc.Col(html.Div([
            html.Div("Take Profit  (2 : 1)", style={"color": C["muted"], "fontSize": "11px",
                                                      "textTransform": "uppercase", "letterSpacing": "0.06em"}),
            html.Div(f"${tp:.2f}", style={"color": C["green"], "fontWeight": "700", "fontSize": "18px"}),
            html.Div(f"{tp_pct:+.1f}% from entry", style={"color": C["muted"], "fontSize": "11px"}),
        ], style={"backgroundColor": f"{C['green']}0d", "border": f"1px solid {C['green']}33",
                   "borderRadius": "8px", "padding": "12px"}), md=6),
    ], className="mb-2 g-3")

    return [indicator_row, sl_tp_row]


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _build_chart(data: dict, ticker: str) -> go.Figure:
    times = data["times"]

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        row_heights=[0.58, 0.18, 0.24],
        vertical_spacing=0.04,
        subplot_titles=(f"{ticker} — Price & VWAP", "Relative Volume", "MACD (12, 26, 9)"),
    )

    # ── Row 1: Candlestick + VWAP ─────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=times,
        open=data["open"], high=data["high"],
        low=data["low"],   close=data["close"],
        name="Price",
        increasing_line_color=C["green"],               decreasing_line_color=C["red"],
        increasing_fillcolor=_hex_rgba(C["green"], 0.27), decreasing_fillcolor=_hex_rgba(C["red"], 0.27),
        showlegend=False,
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=times, y=data["vwap"],
        name="VWAP",
        line={"color": C["amber"], "width": 2, "dash": "dot"},
        mode="lines",
    ), row=1, col=1)

    # ── Row 2: Volume bars (green = up candle, red = down candle) ─────────
    vol_colors = [
        _hex_rgba(C["green"], 0.6) if c >= o else _hex_rgba(C["red"], 0.6)
        for c, o in zip(data["close"], data["open"])
    ]
    fig.add_trace(go.Bar(
        x=times, y=data["volume"],
        name="Volume",
        marker_color=vol_colors,
        showlegend=False,
    ), row=2, col=1)

    # ── Row 3: MACD ───────────────────────────────────────────────────────
    hist_colors = [C["green"] if v >= 0 else C["red"] for v in data["hist"]]
    fig.add_trace(go.Bar(
        x=times, y=data["hist"],
        name="Hist",
        marker_color=hist_colors,
        opacity=0.55,
        showlegend=False,
    ), row=3, col=1)

    fig.add_trace(go.Scatter(
        x=times, y=data["macd"],
        name="MACD",
        line={"color": C["blue"], "width": 1.5},
        mode="lines",
    ), row=3, col=1)

    fig.add_trace(go.Scatter(
        x=times, y=data["signal"],
        name="Signal",
        line={"color": C["amber"], "width": 1.5},
        mode="lines",
    ), row=3, col=1)

    # ── Layout ────────────────────────────────────────────────────────────
    fig.update_layout(
        paper_bgcolor=C["card"],
        plot_bgcolor=C["card"],
        font={"color": C["txt"], "family": FONT, "size": 12},
        height=520,
        margin={"l": 12, "r": 12, "t": 36, "b": 8},
        legend={
            "orientation": "h", "y": 1.06, "x": 0.5, "xanchor": "center",
            "bgcolor": "rgba(0,0,0,0)", "font": {"size": 11},
        },
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        hoverlabel={"bgcolor": C["sidebar"], "font_color": C["txt"], "bordercolor": C["border"]},
        bargap=0.1,
    )
    for row in (1, 2, 3):
        fig.update_xaxes(gridcolor=C["border"], zeroline=False,
                         showline=True, linecolor=C["border"], row=row, col=1)
        fig.update_yaxes(gridcolor=C["border"], zeroline=False,
                         showline=True, linecolor=C["border"], row=row, col=1)

    # Volume y-axis: compact SI suffix
    fig.update_yaxes(tickformat=".2s", row=2, col=1)

    for ann in fig.layout.annotations:
        ann.font.color = C["muted"]
        ann.font.size  = 12

    return fig


# ── Forex callbacks ───────────────────────────────────────────────────────────

@callback(
    Output("selected-forex", "data"),
    Input({"type": "forex-tile", "index": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def set_selected_forex(tile_clicks):
    if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
        raise PreventUpdate
    if not any(v for v in tile_clicks if v):
        raise PreventUpdate
    return ctx.triggered_id["index"]


@callback(
    Output("forex-modal", "is_open"),
    Input("selected-forex", "data"),
    prevent_initial_call=True,
)
def toggle_forex_modal(yf_sym):
    return bool(yf_sym)


@callback(
    Output("forex-modal-title",         "children"),
    Output("forex-modal-body",          "children"),
    Output("forex-modal-chart",         "figure"),
    Output("forex-modal-chart-section", "style"),
    Output("forex-modal-chart-ts",      "children"),
    Output("forex-modal-trade-section", "style"),
    Output("forex-modal-detail",        "data"),
    Input("selected-forex", "data"),
    prevent_initial_call=True,
)
def populate_forex_modal(yf_sym):
    import datetime
    _blank = go.Figure()
    _blank.update_layout(paper_bgcolor=C["card"], plot_bgcolor=C["card"], height=100)

    if not yf_sym:
        raise PreventUpdate
    try:
        detail    = get_forex_detail(yf_sym)
        chart_raw = _get_or_fetch_forex(yf_sym) if not detail.get("error") else None

        if detail.get("error"):
            body = html.Div([
                html.P("⚠  No data available for this pair.",
                       style={"color": C["amber"], "fontWeight": "600"}),
                html.P("yfinance may be rate-limited or the pair is temporarily unavailable.",
                       style={"color": C["muted"], "fontSize": "13px"}),
            ], style={"padding": "20px 0"})
            return yf_sym, body, _blank, _CHART_HIDDEN, "", _TRADE_HIDDEN, None

        label = detail["label"]
        fig   = _build_forex_chart(chart_raw, label) if chart_raw else _blank
        ts    = datetime.datetime.now().strftime("Updated %H:%M:%S · 1H candles")
        body  = _build_forex_modal_body(detail)

        return (
            f"{label}  ·  {detail['current_price']:.5f}" if "JPY" not in yf_sym
            else f"{label}  ·  {detail['current_price']:.3f}",
            body, fig, _CHART_SHOWN, ts, _TRADE_SHOWN, detail,
        )
    except Exception as exc:
        body = html.Div([
            html.P(f"⚠  Error loading {yf_sym}",
                   style={"color": C["red"], "fontWeight": "600"}),
            html.P(str(exc)[:200],
                   style={"color": C["muted"], "fontSize": "12px", "fontFamily": "monospace"}),
        ], style={"padding": "20px 0"})
        return yf_sym, body, _blank, _CHART_HIDDEN, "", _TRADE_HIDDEN, None


@callback(
    Output("selected-forex", "data", allow_duplicate=True),
    Input("forex-modal", "is_open"),
    prevent_initial_call=True,
)
def clear_forex_on_close(is_open):
    if not is_open:
        return None
    raise PreventUpdate


@callback(
    Output("forex-modal-pnl",       "children"),
    Output("oanda-balance-badge",   "children"),
    Input("forex-modal-quantity",   "value"),
    Input("forex-modal-detail",     "data"),   # Input (not State) so it fires when modal opens
    prevent_initial_call=True,
)
def update_forex_pnl(quantity, detail):
    if not detail:
        raise PreventUpdate
    units   = float(quantity or 10000)
    entry   = detail.get("current_price", 0)
    sl      = detail.get("stop_loss",     0)
    tp      = detail.get("take_profit",   0)
    quote   = detail.get("quote",         "")
    yf_sym  = detail.get("yf",            "")
    if not entry:
        raise PreventUpdate

    # Fetch OANDA account balance for the badge (non-blocking — cached by the session)
    try:
        acct      = oanda.get_account_summary()
        bal       = float(acct.get("balance", 0))
        acct_ccy  = acct.get("currency", "GBP")
        bal_badge = html.Span(
            f"Balance: {bal:,.2f} {acct_ccy}",
            style={"backgroundColor": f"{C['blue']}18", "color": C["blue"],
                   "border": f"1px solid {C['blue']}44", "borderRadius": "4px",
                   "fontSize": "11px", "fontWeight": "600", "padding": "2px 8px"},
        )
    except Exception:
        bal_badge = None

    is_jpy   = "JPY" in yf_sym
    pip_size = 0.01 if is_jpy else 0.0001

    pips_to_tp  = max(1, round((tp - entry) / pip_size))
    pips_to_sl  = max(1, round((entry - sl) / pip_size))
    pip_val     = units * pip_size          # value of 1 pip for this position, in quote currency
    profit      = units * (tp - entry)
    loss        = units * (entry - sl)
    rr          = round(profit / loss, 1) if loss else 0

    price_fmt   = f"{entry:.3f}" if is_jpy else f"{entry:.5f}"
    margin      = (units * entry) / 30      # approx at 30:1 leverage

    _lbl = {"fontSize": "10px", "textTransform": "uppercase", "letterSpacing": "0.07em",
            "color": C["muted"], "marginBottom": "3px"}
    _card_base = {"borderRadius": "7px", "padding": "9px 12px"}

    return html.Div([
        # ── Summary line ──────────────────────────────────────────────────────
        html.Div([
            html.Span(f"{units:,.0f} units",
                      style={"color": C["txt"], "fontWeight": "700", "fontSize": "14px"}),
            html.Span(f"  ·  Entry {price_fmt}",
                      style={"color": C["muted"], "fontSize": "13px"}),
            html.Span(f"  ·  ~{margin:,.0f} {quote} margin (30:1 est.)",
                      style={"color": C["dim"] if quote else C["muted"],
                             "fontSize": "11px", "color": "#4b5563"}),
        ], style={"marginBottom": "10px"}),

        # ── Pip info cards ────────────────────────────────────────────────────
        dbc.Row([
            dbc.Col(html.Div([
                html.Div("Pips to TP", style=_lbl),
                html.Div(f"+{pips_to_tp}",
                         style={"color": C["green"], "fontWeight": "700", "fontSize": "18px",
                                "lineHeight": "1"}),
                html.Div("pips", style={"color": C["muted"], "fontSize": "10px"}),
            ], style={**_card_base,
                       "backgroundColor": f"{C['green']}08",
                       "border": f"1px solid {C['green']}22"}), md=4),

            dbc.Col(html.Div([
                html.Div("Pips to SL", style=_lbl),
                html.Div(f"−{pips_to_sl}",
                         style={"color": C["red"], "fontWeight": "700", "fontSize": "18px",
                                "lineHeight": "1"}),
                html.Div("pips", style={"color": C["muted"], "fontSize": "10px"}),
            ], style={**_card_base,
                       "backgroundColor": f"{C['red']}08",
                       "border": f"1px solid {C['red']}22"}), md=4),

            dbc.Col(html.Div([
                html.Div("Pip Value", style=_lbl),
                html.Div(f"{pip_val:.2f}",
                         style={"color": C["txt"], "fontWeight": "700", "fontSize": "18px",
                                "lineHeight": "1"}),
                html.Div(f"{quote}/pip", style={"color": C["muted"], "fontSize": "10px"}),
            ], style={**_card_base,
                       "backgroundColor": C["card"],
                       "border": f"1px solid {C['border']}"}), md=4),
        ], className="g-2 mb-3"),

        # ── Profit / Risk boxes ───────────────────────────────────────────────
        dbc.Row([
            dbc.Col(html.Div([
                html.Div("Profit at TP", style={**_lbl, "marginBottom": "5px"}),
                html.Div(f"+{profit:,.2f} {quote}",
                         style={"color": C["green"], "fontWeight": "700", "fontSize": "22px",
                                "lineHeight": "1.1"}),
                html.Div(f"+{pips_to_tp} pips × {pip_val:.2f} {quote}/pip",
                         style={"color": C["muted"], "fontSize": "11px", "marginTop": "4px"}),
            ], style={**_card_base,
                       "backgroundColor": f"{C['green']}0d",
                       "border": f"1px solid {C['green']}33",
                       "borderRadius": "9px", "padding": "12px 14px"}), md=6),

            dbc.Col(html.Div([
                html.Div("Risk at SL", style={**_lbl, "marginBottom": "5px"}),
                html.Div(f"−{loss:,.2f} {quote}",
                         style={"color": C["red"], "fontWeight": "700", "fontSize": "22px",
                                "lineHeight": "1.1"}),
                html.Div(f"−{pips_to_sl} pips × {pip_val:.2f} {quote}/pip",
                         style={"color": C["muted"], "fontSize": "11px", "marginTop": "4px"}),
            ], style={**_card_base,
                       "backgroundColor": f"{C['red']}0d",
                       "border": f"1px solid {C['red']}33",
                       "borderRadius": "9px", "padding": "12px 14px"}), md=6),
        ], className="g-2"),

        # ── R:R badge + footnote ──────────────────────────────────────────────
        html.Div([
            html.Span(f"R:R {rr}:1",
                      style={"backgroundColor": f"{C['blue']}22", "color": C["blue"],
                             "border": f"1px solid {C['blue']}44", "borderRadius": "4px",
                             "fontSize": "11px", "fontWeight": "700", "padding": "2px 7px",
                             "marginRight": "8px"}),
            html.Span(
                f"P&L shown in {quote}. OANDA converts to your account currency on fill.",
                style={"color": C["muted"], "fontSize": "10px", "fontStyle": "italic"},
            ),
        ], style={"marginTop": "9px"}),
    ]), bal_badge


@callback(
    Output("forex-modal-trade-result", "children"),
    Input("forex-modal-buy-btn",  "n_clicks"),
    Input("forex-modal-sell-btn", "n_clicks"),
    State("forex-modal-quantity", "value"),
    State("selected-forex",       "data"),
    State("forex-modal-detail",   "data"),
    prevent_initial_call=True,
)
def place_forex_trade(buy_clicks, sell_clicks, quantity, yf_sym, detail):
    if not ctx.triggered_id or not yf_sym or not quantity or not detail:
        raise PreventUpdate
    side       = "BUY" if ctx.triggered_id == "forex-modal-buy-btn" else "SELL"
    units      = abs(float(quantity)) * (1 if side == "BUY" else -1)
    pair_label = detail.get("label", "")
    instrument = OandaClient.yf_to_instrument(yf_sym)

    entry = detail.get("current_price", 0)
    atr   = detail.get("atr", 0)

    if side == "BUY":
        sl = detail.get("stop_loss")
        tp = detail.get("take_profit")
    else:
        # Flip SL/TP for a SELL (short): price needs to fall to reach TP
        is_jpy = "JPY" in yf_sym
        decimals = 3 if is_jpy else 5
        sl = round(entry + atr,      decimals) if entry and atr else None
        tp = round(entry - 2 * atr,  decimals) if entry and atr else None

    result = oanda.place_market_order(instrument, units, stop_loss=sl, take_profit=tp)

    if "error" in result:
        detail_msg = result.get("detail", "")[:120]
        return html.Div([
            html.Span("✗  Order failed: ", style={"color": C["red"], "fontWeight": "700"}),
            html.Span(result["error"][:80], style={"color": C["red"]}),
            html.Div(detail_msg, style={"color": C["muted"], "fontSize": "11px", "marginTop": "4px"})
            if detail_msg else None,
        ])

    fill      = result.get("orderFillTransaction", {})
    order_tx  = result.get("orderCreateTransaction", {})
    order_id  = fill.get("id") or order_tx.get("id", "—")
    fill_price = fill.get("price", "—")
    sl_str    = f" · SL {sl}" if sl else ""
    tp_str    = f" · TP {tp}" if tp else ""

    return html.Div([
        html.Span("✓ ", style={"color": C["green"], "fontWeight": "700", "fontSize": "16px"}),
        html.Span(
            f"{side} {abs(units):,.0f} units {pair_label}",
            style={"color": C["green"], "fontWeight": "700"},
        ),
        html.Div(
            f"Filled @ {fill_price}{sl_str}{tp_str}  ·  Order #{order_id}  ·  via OANDA",
            style={"color": C["muted"], "fontSize": "11px", "marginTop": "3px"},
        ),
    ])


# ── Auto-trader callbacks ─────────────────────────────────────────────────────

@callback(
    Output("trader-state", "data"),
    Input("trader-poll",   "n_intervals"),
    Input("active-page",   "data"),
)
def poll_trader_state(n_intervals, active_page):
    return get_trader().get_state()


@callback(
    Output("main-content", "children", allow_duplicate=True),
    Input("trader-state",  "data"),
    State("active-page",   "data"),
    prevent_initial_call=True,
)
def render_auto_page_from_state(trader_state, active_page):
    if active_page != "auto":
        raise PreventUpdate
    return render_autotrader(trader_state or {})


@callback(
    Output("trader-state", "data", allow_duplicate=True),
    Input({"type": "confirm-signal", "index": dash.ALL}, "n_clicks"),
    Input({"type": "dismiss-signal", "index": dash.ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_signal_action(confirm_clicks, dismiss_clicks):
    if not ctx.triggered_id or not isinstance(ctx.triggered_id, dict):
        raise PreventUpdate
    all_clicks = (confirm_clicks or []) + (dismiss_clicks or [])
    if not any(v for v in all_clicks if v):
        raise PreventUpdate
    ticker      = ctx.triggered_id["index"]
    action_type = ctx.triggered_id["type"]
    trader      = get_trader()
    if action_type == "confirm-signal":
        trader.confirm_signal(ticker)
    elif action_type == "dismiss-signal":
        trader.dismiss_signal(ticker)
    return trader.get_state()


@callback(
    Output("chart-container", "style"),
    Output("chart-title",     "children"),
    Output("stock-chart",     "figure"),
    Input("screener-table", "selected_rows"),
    State("screener-table", "data"),
    prevent_initial_call=True,
)
def update_stock_chart(selected_rows, table_data):
    if not selected_rows or not table_data:
        raise PreventUpdate

    ticker = table_data[selected_rows[0]]["Ticker"]
    chart_data = get_chart_data(ticker)

    if chart_data is None:
        empty_fig = go.Figure()
        empty_fig.update_layout(
            paper_bgcolor=C["card"], plot_bgcolor=C["card"],
            font_color=C["muted"], height=200,
            annotations=[{"text": "No intraday data available", "showarrow": False,
                           "font": {"size": 14, "color": C["muted"]}}],
        )
        return (
            {**CARD, "display": "block", "position": "relative"},
            ticker,
            empty_fig,
        )

    return (
        {**CARD, "display": "block", "position": "relative", "padding": "20px"},
        ticker,
        _build_chart(chart_data, ticker),
    )


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050, threaded=True)
