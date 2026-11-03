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


def previous_close(ticker: str, day=None) -> float | None:
    """The last saved close before `day` (the date of the current price), for today's change."""
    series = closes(ticker)
    if series is None or series.empty:
        return None
    if day is not None and series.index[-1].date() >= day and len(series) > 1:
        return float(series.iloc[-2])
    return float(series.iloc[-1])


def day_change_html(ticker: str, price: float, as_of) -> str:
    """A stock's change since the previous close, as colored percent text, or "" if unknown."""
    previous = previous_close(ticker, pd.Timestamp(as_of).date() if as_of else None)
    if not previous or price is None:
        return ""
    change = price / previous - 1
    return f"<span class='{direction(change)}'>{change:+.2%}</span>"


def today_change(owner: str, performance) -> tuple[float, float]:
    """The account's change today in dollars and percent: now against the last saved close.

    On the day an account opens, that is the change since opening.
    """
    history = value_history(owner)
    times = pd.to_datetime(history["time"], utc=True).dt.tz_convert("America/New_York")
    today = pd.Timestamp.now(tz="America/New_York").date()
    earlier = history[times.dt.date < today]
    start = float(earlier["account"].iloc[-1]) if len(earlier) else float(history["account"].iloc[0])
    amount = performance.account_value - start
    return amount, (amount / start * 100 if start else 0.0)


def account_hero(label: str, owner: str, performance, starting_cash: float):
    """The big account value with its change today and since opening, like a trading app."""
    today_amount, today_percent = today_change(owner, performance)
    total = performance.account_value - starting_cash
    hero(label, money(performance.account_value),
         change_html(today_amount, today_percent, "today") + "<br>"
         + change_html(total, performance.account_gain_percent, "since opening"))


def toggle_watch(ticker: str):
    watchlist = storage.load_watchlist()
    if ticker in watchlist:
        watchlist.remove(ticker)
    else:
        watchlist.append(ticker)
    storage.save_watchlist(watchlist)


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


# More charts, modeled on what trading sites show

SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"]  # categorical, in fixed order


def market_snapshot() -> pd.DataFrame:
    """Every S&P 500 stock's last saved close and its change over 1 day and about 1 month.

    Worked out once a day and kept on disk, so it is quick even after the site restarts.
    """
    results = storage.latest_results()
    return _market_snapshot(results.date if results else str(date.today()), str(storage.data_dir()))


@st.cache_data(persist="disk", show_spinner="Loading market data (once a day)…")
def _market_snapshot(day: str, folder: str) -> pd.DataFrame:
    # `day` and `folder` only key the cache: a new day, or another data folder, starts afresh.
    sp500 = storage.load_sp500()
    rows = []
    for ticker, name, sector in zip(sp500["ticker"], sp500["company_name"], sp500["sector"]):
        history = storage.load_prices(ticker)
        if history is None or len(history) < 22:
            continue
        close = history["close"]
        rows.append({"ticker": ticker, "company": name, "sector": sector, "date": close.index[-1],
                     "close": float(close.iloc[-1]),
                     "change_1d": float(close.iloc[-1] / close.iloc[-2] - 1),
                     "change_1m": float(close.iloc[-1] / close.iloc[-22] - 1)})
    table = pd.DataFrame(rows)
    latest = table["date"].max()
    return table[table["date"] == latest].reset_index(drop=True)  # leave out stocks with stale prices


def _weekly(table: pd.DataFrame) -> pd.DataFrame:
    weekly = table.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                          "volume": "sum", "avg_50": "last", "avg_200": "last"})
    return weekly.dropna(subset=["close"])


def stock_chart(history: pd.DataFrame, days: int | None, style: str, averages: list[str], height=320):
    """Price as a line or candles, optional moving averages, and volume bars underneath.

    Averages are worked out on the full history first, so they are right at the
    start of the chosen range. Candles over more than about a year are weekly.
    """
    table = history[["open", "high", "low", "close", "volume"]].copy()
    table["avg_50"] = table["close"].rolling(50).mean()
    table["avg_200"] = table["close"].rolling(200).mean()
    table = table.iloc[-days:] if days else table
    weekly = style == "Candles" and len(table) > 300
    if weekly:
        table = _weekly(table)
    data = table.rename_axis("date").reset_index()
    data["up"] = data["close"] >= data["open"]
    x = alt.X("date:T", title=None, axis=alt.Axis(grid=False, format="%b %d '%y"))
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", empty=False, clear="pointerout")
    base = alt.Chart(data).encode(x=x)
    y_axis = alt.Axis(format="$,.0f", tickCount=5)
    up_down = alt.condition("datum.up", alt.value(GREEN), alt.value(RED))

    if style == "Candles":
        wick = base.mark_rule(strokeWidth=1).encode(
            y=alt.Y("low:Q", title=None, scale=alt.Scale(zero=False), axis=y_axis), y2="high:Q", color=up_down)
        body = base.mark_bar(width={"band": 0.7}).encode(y="open:Q", y2="close:Q", color=up_down)
        layers = [wick, body]
    else:
        color = GREEN if data["close"].iloc[-1] >= data["close"].iloc[0] else RED
        layers = [base.mark_line(color=color, strokeWidth=2).encode(
            y=alt.Y("close:Q", title=None, scale=alt.Scale(zero=False), axis=y_axis))]

    names = {"50-day average": "avg_50", "200-day average": "avg_200"}
    if averages:
        shown = data[["date"] + [names[a] for a in averages]].rename(columns={v: k for k, v in names.items()})
        layers.append(alt.Chart(shown.melt("date", var_name="line", value_name="value").dropna()).mark_line(
            strokeWidth=1.5).encode(
            x="date:T", y="value:Q",
            color=alt.Color("line:N", scale=alt.Scale(domain=list(names), range=[BLUE, ORANGE]),
                            legend=alt.Legend(orient="top", title=None))))

    rule = base.mark_rule(color=MUTED).encode(
        opacity=alt.condition(hover, alt.value(0.6), alt.value(0)),
        tooltip=[alt.Tooltip("date:T", title="Week ending" if weekly else "Date", format="%b %d, %Y"),
                 alt.Tooltip("open:Q", title="Open", format="$,.2f"),
                 alt.Tooltip("high:Q", title="High", format="$,.2f"),
                 alt.Tooltip("low:Q", title="Low", format="$,.2f"),
                 alt.Tooltip("close:Q", title="Close", format="$,.2f"),
                 alt.Tooltip("volume:Q", title="Volume", format=",.0f")],
    ).add_params(hover)
    price = alt.layer(*layers, rule).properties(height=height)
    volume = base.mark_bar(opacity=0.5).encode(
        y=alt.Y("volume:Q", title=None, axis=alt.Axis(format="~s", tickCount=2)), color=up_down,
    ).properties(height=70)
    st.altair_chart(_axis_config(alt.vconcat(price, volume, spacing=4).resolve_scale(x="shared")), width="stretch")
    st.caption(f"Bars underneath show volume: how many shares traded each {'week' if weekly else 'day'}. "
               + ("Green means the price closed higher than it opened; red, lower." if style == "Candles" else ""))


def contributions_chart(contributions: list):
    """What pushed the chance of rising up (green, +) or down (red, −), largest first."""
    data = pd.DataFrame([{"Input": c.label, "Effect": c.effect, "Value": c.value} for c in contributions])
    if data.empty:
        return
    data["Direction"] = data["Effect"].map(lambda e: "Pushed up" if e >= 0 else "Pushed down")
    order = list(data.sort_values("Effect", key=abs, ascending=False)["Input"])
    bars = alt.Chart(data).mark_bar(cornerRadius=3, height=14).encode(
        x=alt.X("Effect:Q", title="Effect on the chance of rising (percentage points)"),
        y=alt.Y("Input:N", sort=order, title=None, axis=alt.Axis(labelLimit=260)),
        color=alt.Color("Direction:N", scale=alt.Scale(domain=["Pushed up", "Pushed down"], range=[GREEN, RED])),
        tooltip=["Input", alt.Tooltip("Value:Q", format=",.4f"), alt.Tooltip("Effect:Q", format="+.2f")],
    )
    labels = bars.mark_text(align="left", dx=4, fontSize=11).encode(
        text=alt.Text("Effect:Q", format="+.1f"), color=alt.value(TEXT_SECONDARY))
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=MUTED).encode(x="x:Q")
    st.altair_chart(_axis_config(alt.layer(bars, labels, zero).properties(height=max(120, 24 * len(data)))),
                    width="stretch")


def allocation_chart(parts: dict, height=240):
    """A donut of where the money is. Past 6 holdings the smallest fold into "Other"; cash is gray."""
    parts = dict(parts)
    cash = parts.pop("Cash", 0.0)
    ordered = sorted(parts.items(), key=lambda item: item[1], reverse=True)
    shown = ordered[:5] if len(ordered) > 6 else ordered
    rest = sum(value for _, value in ordered[len(shown):])
    rows = [{"part": name, "value": value} for name, value in shown]
    if rest:
        rows.append({"part": "Other", "value": rest})
    if cash:
        rows.append({"part": "Cash", "value": cash})
    data = pd.DataFrame(rows)
    data["share"] = data["value"] / data["value"].sum()
    domain = list(data["part"])
    colors = SERIES[:len(shown)] + ([MUTED] if rest else []) + (["#5c5b56"] if cash else [])
    chart = alt.Chart(data).mark_arc(innerRadius=60, stroke="#0d0d0d", strokeWidth=2).encode(
        theta="value:Q",
        color=alt.Color("part:N", sort=domain, scale=alt.Scale(domain=domain, range=colors),
                        legend=alt.Legend(orient="right", title=None)),
        order=alt.Order("value:Q", sort="descending"),
        tooltip=[alt.Tooltip("part:N", title="Holding"), alt.Tooltip("value:Q", title="Value", format="$,.2f"),
                 alt.Tooltip("share:Q", title="Share", format=".1%")],
    ).properties(height=height)
    st.altair_chart(_axis_config(chart), width="stretch")


def change_bars(data: pd.DataFrame, label: str, value: str, title=None, row_height=22):
    """Horizontal bars of a percent change per row: green for up, red for down, labeled with the sign."""
    data = data.copy()
    data["Direction"] = data[value].map(lambda v: "Up" if v >= 0 else "Down")
    bars = alt.Chart(data).mark_bar(cornerRadius=3, height=14).encode(
        x=alt.X(f"{value}:Q", title=title, axis=alt.Axis(format="+.1%")),
        y=alt.Y(f"{label}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
        color=alt.Color("Direction:N", scale=alt.Scale(domain=["Up", "Down"], range=[GREEN, RED]), legend=None),
        tooltip=[alt.Tooltip(f"{label}:N"), alt.Tooltip(f"{value}:Q", format="+.2%")],
    )
    labels = bars.mark_text(align="left", dx=4, fontSize=11).encode(
        text=alt.Text(f"{value}:Q", format="+.1%"), color=alt.value(TEXT_SECONDARY))
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=MUTED).encode(x="x:Q")
    st.altair_chart(_axis_config(alt.layer(bars, labels, zero).properties(height=max(100, row_height * len(data)))),
                    width="stretch")


def leaderboard_chart(entries: list[tuple[str, float, str]]):
    """Return since opening (in percent) for each account, one bar each, in that account's own color."""
    data = pd.DataFrame([{"Account": name, "Return": value / 100, "color": color} for name, value, color in entries])
    bars = alt.Chart(data).mark_bar(cornerRadius=3, height=18).encode(
        x=alt.X("Return:Q", title="Return since opening", axis=alt.Axis(format="+.1%")),
        y=alt.Y("Account:N", sort=[e[0] for e in entries], title=None),
        color=alt.Color("color:N", scale=None, legend=None),
        tooltip=["Account", alt.Tooltip("Return:Q", format="+.2%")],
    )
    labels = bars.mark_text(align="left", dx=4, fontSize=12).encode(
        text=alt.Text("Return:Q", format="+.2%"), color=alt.value(TEXT_SECONDARY))
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=MUTED).encode(x="x:Q")
    st.altair_chart(_axis_config(alt.layer(bars, labels, zero).properties(height=40 * len(data))), width="stretch")


def calibration_chart(calibration: list[dict]):
    """How often stocks really rose, against the chance the model gave. The dashed line is perfect."""
    rows = []
    for bucket in calibration:
        low, high = (float(part.strip().rstrip("%")) / 100 for part in bucket["bucket"].split(" to "))
        rows.append({"Chance given": (low + high) / 2, "Actually rose": bucket["rose_share"],
                     "Forecasts": bucket["forecasts"], "Range": bucket["bucket"]})
    data = pd.DataFrame(rows)
    scale = alt.Scale(domain=[0, 1])
    perfect = alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]})).mark_line(
        color=MUTED, strokeDash=[4, 4], strokeWidth=1).encode(x=alt.X("x:Q", scale=scale), y=alt.Y("y:Q", scale=scale))
    line = alt.Chart(data).mark_line(color=BLUE, strokeWidth=2, point=alt.OverlayMarkDef(size=80, filled=True)).encode(
        x=alt.X("Chance given:Q", scale=scale, axis=alt.Axis(format=".0%"), title="Chance the AI gave"),
        y=alt.Y("Actually rose:Q", scale=scale, axis=alt.Axis(format=".0%"), title="How often it really rose"),
        tooltip=["Range", alt.Tooltip("Actually rose:Q", format=".1%"), alt.Tooltip("Forecasts:Q", format=",")],
    )
    st.altair_chart(_axis_config(alt.layer(perfect, line).properties(height=300)), width="stretch")
    st.caption("If the AI's percentages meant what they say, the blue line would sit on the dashed line.")
