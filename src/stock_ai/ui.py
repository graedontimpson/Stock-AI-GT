"""Pieces shared by the website's pages: layout, formatting, charts, and cached reads."""

from datetime import date, datetime

import altair as alt
import pandas as pd
import streamlit as st

from stock_ai import account, pipeline, storage
from stock_ai.data import prices
from stock_ai.errors import PriceUnavailableError, StockAIError

DISCLAIMER = ("Suggestions are estimates from past prices, not guarantees. "
              "All money on this site is pretend.")

# Colors, matching .streamlit/config.toml. Green and red mean up and down, and
# always come with a + or − sign so color is never the only cue.
GREEN = "#0ca30c"
RED = "#e66767"
BLUE = "#3987e5"
ORANGE = "#d95926"
MUTED = "#898781"
GRID = "#2c2c2a"
TEXT_SECONDARY = "#c3c2b7"

ACTIONS = {
    "buy": ("green", ":material/trending_up:", "Buy"),
    "sell": ("red", ":material/trending_down:", "Sell"),
    "hold": ("gray", ":material/pause:", "Hold"),
}

CSS = """
<style>
.block-container {max-width: 1280px;}
.hero-label {color: #c3c2b7; font-size: 0.9rem; margin-bottom: -0.2rem;}
.hero-value {font-size: 2.6rem; font-weight: 600; line-height: 1.15; letter-spacing: -0.02em;}
.hero-change {font-size: 1rem; margin-top: 0.15rem;}
.up {color: #0ca30c;} .down {color: #e66767;} .flat {color: #c3c2b7;}
.muted {color: #898781; font-size: 0.85rem;}
.stat-label {color: #898781; font-size: 0.8rem;}
.stat-value {font-size: 1.05rem; font-weight: 500;}
</style>
"""


# Page layout

def page(title: str):
    """Common page setup: styles, the title row with search, and the market status."""
    st.html(CSS)
    left, right = st.columns([3, 2], vertical_alignment="center")
    left.title(title)
    with right:
        search_box(key=f"search-{title}")
    _market_status()


def _market_status():
    is_open = prices.market_is_open(datetime.now(prices.NEW_YORK))
    if is_open:
        st.badge("Market open · prices may be about 15 minutes old", icon=":material/schedule:", color="green")
    else:
        st.badge("Market closed · trades use the last closing price", icon=":material/bedtime:", color="gray")


def search_box(key: str):
    """Search the S&P 500 by ticker or company name; picking one opens its stock page."""
    sp500 = storage.load_sp500()
    if sp500 is None:
        return
    names = dict(zip(sp500["ticker"], sp500["company_name"]))
    choice = st.selectbox("Search", list(names), index=None, key=key, label_visibility="collapsed",
                          format_func=lambda t: f"{t} · {names[t]}",
                          placeholder="🔍 Search stocks by ticker or name")
    if choice:
        st.session_state.pop(key, None)
        open_stock(choice)


def footer():
    st.divider()
    st.caption(DISCLAIMER)


def open_stock(ticker: str):
    st.switch_page("pages/stock.py", query_params={"ticker": ticker})


# Formatting

def money(value) -> str:
    return "—" if value is None else f"${value:,.2f}"


def percent(value, digits=1, sign=False) -> str:
    """Formats a fraction (0.25) as a percent (25.0%)."""
    if value is None:
        return "—"
    return f"{value * 100:+.{digits}f}%" if sign else f"{value * 100:.{digits}f}%"


def direction(value) -> str:
    if value is None or abs(value) < 1e-9:
        return "flat"
    return "up" if value > 0 else "down"


def change_html(amount, percent_points, suffix="") -> str:
    """A colored "+$12.34 (+1.23%) suffix" line. percent_points is already in percent."""
    arrow = {"up": "▲", "down": "▼", "flat": ""}[direction(amount)]
    sign = "+" if amount >= 0 else "−"
    text = f"{arrow} {sign}${abs(amount):,.2f} ({percent_points:+.2f}%)"
    return f'<span class="{direction(amount)}">{text}</span> <span class="muted">{suffix}</span>'


def hero(label: str, value: str, change: str = ""):
    st.markdown(f'<div class="hero-label">{label}</div><div class="hero-value">{value}</div>'
                f'<div class="hero-change">{change}</div>', unsafe_allow_html=True)


def stat(column, label: str, value: str):
    column.markdown(f'<div class="stat-label">{label}</div><div class="stat-value">{value}</div>',
                    unsafe_allow_html=True)


def action_badge(action: str) -> str:
    """Markdown for a colored Buy / Hold / Sell badge, or a dash when there is none."""
    if action not in ACTIONS:
        return "—"
    color, icon, label = ACTIONS[action]
    return f":{color}-badge[{icon} {label}]"


def action_text(action: str) -> str:
    return ACTIONS[action][2] if action in ACTIONS else "—"


# Data, cached so moving between pages stays quick. Anything that a trade
# changes is cleared by `refresh_account`.

def daily_results():
    """Today's results, running the daily update first if it hasn't run yet today."""
    saved = storage.load_results(str(date.today()))
    if saved is not None:
        return saved
    first_run = storage.load_prices("SPY") is None
    label = ("First run: downloading 10 years of prices for about 500 stocks. "
             "This takes several minutes." if first_run else "Running today's update…")
    with st.status(label, expanded=True) as status:
        try:
            results = pipeline.run_daily(progress=status.write)
        except StockAIError as error:
            status.update(label="The update didn't finish", state="error")
            latest = storage.latest_results()
            st.warning(error.message)
            return latest
        status.update(label="Today's update is done", state="complete", expanded=False)
    refresh_account()
    return results


def ensure_account():
    try:
        return account.open_account()
    except StockAIError as error:
        st.error(error.message)
        st.stop()


@st.cache_data(ttl=60, show_spinner=False)
def quote(ticker: str):
    """The latest price for display, or None. Trades always fetch their own fresh price."""
    try:
        return prices.get_latest_price(ticker)
    except PriceUnavailableError:
        return None


@st.cache_data(ttl=60, show_spinner=False)
def portfolio_and_performance(owner: str = "you"):
    portfolio = account.get_portfolio(owner)
    return portfolio, account.get_performance(portfolio, owner)


@st.cache_data(ttl=600, show_spinner=False)
def value_history(owner: str = "you") -> pd.DataFrame:
    return pd.DataFrame(account.get_value_history(owner))


def value_history_with_today(owner: str, performance) -> pd.DataFrame:
    """Saved daily values plus today's live value, with times in New York time."""
    live = pd.DataFrame([{"time": pd.Timestamp.now(tz="America/New_York"),
                          "account": performance.account_value, "benchmark": performance.benchmark_value}])
    history = pd.concat([value_history(owner), live], ignore_index=True)
    history["time"] = pd.to_datetime(history["time"], utc=True).dt.tz_convert("America/New_York")
    return history


def last_days(history: pd.DataFrame, choice: str) -> pd.DataFrame:
    days = RANGES[choice]
    if days is None:
        return history
    return history[history["time"] >= history["time"].iloc[-1] - pd.Timedelta(days=days * 7 / 5)]


@st.cache_data(ttl=600, show_spinner=False)
def closes(ticker: str) -> pd.Series | None:
    history = storage.load_prices(ticker)
    return None if history is None else history["close"]


def refresh_account():
    portfolio_and_performance.clear()
    value_history.clear()


def previous_close(ticker: str, live) -> float | None:
    """The close before the live price's day, for today's change."""
    series = closes(ticker)
    if series is None or series.empty:
        return None
    if live is not None and series.index[-1].date() >= live.as_of.date() and len(series) > 1:
        return float(series.iloc[-2])
    return float(series.iloc[-1])


# Charts

RANGES = {"1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252, "5Y": 1260, "All": None}


def range_picker(key: str, options=("1M", "3M", "6M", "1Y", "5Y", "All"), default="1Y") -> str:
    choice = st.segmented_control("Range", list(options), default=default, key=key,
                                  label_visibility="collapsed")
    return choice or default


def _axis_config(chart: alt.Chart) -> alt.Chart:
    return (chart.configure_view(strokeWidth=0)
            .configure_axis(gridColor=GRID, domainColor=GRID, tickColor=GRID,
                            labelColor=MUTED, titleColor=MUTED, labelFontSize=11)
            .configure_legend(labelColor=TEXT_SECONDARY, titleColor=MUTED, orient="top", title=None))


def price_chart(series: pd.Series, height=320, label="Price"):
    """One price line, green if it ended higher than it started and red if lower, with a hover crosshair."""
    data = series.rename("value").rename_axis("date").reset_index()
    color = GREEN if data["value"].iloc[-1] >= data["value"].iloc[0] else RED
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", empty=False, clear="pointerout")
    base = alt.Chart(data).encode(x=alt.X("date:T", title=None, axis=alt.Axis(grid=False, format="%b %d '%y")))
    line = base.mark_line(color=color, strokeWidth=2).encode(
        y=alt.Y("value:Q", title=None, scale=alt.Scale(zero=False), axis=alt.Axis(format="$,.0f", tickCount=5)))
    rule = base.mark_rule(color=MUTED).encode(
        opacity=alt.condition(hover, alt.value(0.6), alt.value(0)),
        tooltip=[alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
                 alt.Tooltip("value:Q", title=label, format="$,.2f")],
    ).add_params(hover)
    point = line.mark_point(color=color, filled=True, size=70).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0)))
    st.altair_chart(_axis_config(alt.layer(line, rule, point).properties(height=height)), width="stretch")


YOU_AND_MARKET = {"account": ("Your account", BLUE), "benchmark": ("S&P 500 (SPY)", MUTED)}


def comparison_chart(history: pd.DataFrame, lines: dict = YOU_AND_MARKET, height=300):
    """Account values on one dollar axis. `lines` maps a column to its (label, color)."""
    wide = history[["time", *lines]].rename(columns={col: label for col, (label, _) in lines.items()})
    labels = [label for label, _ in lines.values()]
    data = wide.melt("time", var_name="series", value_name="value").dropna()
    hover = alt.selection_point(fields=["time"], nearest=True, on="pointerover", empty=False, clear="pointerout")
    color = alt.Color("series:N", sort=labels,
                      scale=alt.Scale(domain=labels, range=[c for _, c in lines.values()]))
    base = alt.Chart(data).encode(x=alt.X("time:T", title=None, axis=alt.Axis(grid=False, format="%b %d")))
    drawn = base.mark_line(strokeWidth=2).encode(
        y=alt.Y("value:Q", title=None, scale=alt.Scale(zero=False), axis=alt.Axis(format="$,.0f", tickCount=5)),
        color=color,
    )
    rule = alt.Chart(wide).mark_rule(color=MUTED).encode(
        x="time:T",
        opacity=alt.condition(hover, alt.value(0.6), alt.value(0)),
        tooltip=[alt.Tooltip("time:T", title="Date", format="%b %d, %Y")]
                + [alt.Tooltip(f"{label}:Q", format="$,.2f") for label in labels],
    ).add_params(hover)
    points = drawn.mark_point(filled=True, size=60).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0)))
    st.altair_chart(_axis_config(alt.layer(drawn, rule, points).properties(height=height)), width="stretch")


def sparkline(series: pd.Series, height=36):
    """A tiny trend line with no axes, colored by whether it ended up or down."""
    data = series.rename("value").rename_axis("date").reset_index()
    color = GREEN if data["value"].iloc[-1] >= data["value"].iloc[0] else RED
    chart = alt.Chart(data).mark_line(color=color, strokeWidth=1.5).encode(
        x=alt.X("date:T", axis=None), y=alt.Y("value:Q", axis=None, scale=alt.Scale(zero=False)),
    ).properties(height=height).configure_view(strokeWidth=0)
    st.altair_chart(chart, width="stretch")
