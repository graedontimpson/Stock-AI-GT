import pandas as pd
import streamlit as st

from stock_ai import account, pipeline, storage, ui
from stock_ai.errors import StockAIError

ui.page("Stocks")
results = ui.daily_results()
ui.ensure_account()

sp500 = storage.load_sp500()
if sp500 is None:
    st.error("The S&P 500 list isn't available yet. Open the Home page to run the first update.")
    st.stop()
names = dict(zip(sp500["ticker"], sp500["company_name"]))
sectors = dict(zip(sp500["ticker"], sp500["sector"]))

# The stock to show comes from the address (stock?ticker=AAPL), so a stock page can be bookmarked.
ticker = st.query_params.get("ticker", "").strip().upper() or None
if ticker and ticker not in names:
    st.warning(f"{ticker} isn't in the S&P 500. This site only trades S&P 500 stocks.")
    st.query_params.clear()
    ticker = None


def browse():
    """No stock chosen: a sortable list of every S&P 500 stock. Clicking a row opens it."""
    st.subheader("Browse the S&P 500")
    st.caption("Click a row to open the stock, or use the search box above. Click a column title to sort.")
    market = ui.market_snapshot().set_index("ticker")
    rows = []
    for t, name in names.items():
        suggestion = results.find(t) if results else None
        moves = market.loc[t] if t in market.index else None
        rows.append({
            "Ticker": t, "Company": name, "Sector": sectors[t],
            "Price": moves["close"] if moves is not None else None,
            "Last day": moves["change_1d"] * 100 if moves is not None else None,
            "AI suggestion": ui.action_text(suggestion.action) if suggestion else "—",
            "Chance of rising": suggestion.probability_up * 100 if suggestion else None,
            "Risk": suggestion.risk.capitalize() if suggestion else "—",
        })
    table = pd.DataFrame(rows)
    sector = st.pills("Sector", sorted(table["Sector"].unique()), label_visibility="collapsed")
    if sector:
        table = table[table["Sector"] == sector].reset_index(drop=True)
    event = st.dataframe(
        table, hide_index=True, width="stretch", height=560, on_select="rerun", selection_mode="single-row",
        column_config={
            "Price": st.column_config.NumberColumn(format="dollar"),
            "Last day": st.column_config.NumberColumn("Last day's change", format="%+.2f%%"),
            "Chance of rising": st.column_config.ProgressColumn(
                "Chance of rising in 3 months", format="%.0f%%", min_value=0, max_value=100)},
    )
    if event.selection.rows:
        ui.open_stock(table.iloc[event.selection.rows[0]]["Ticker"])


if ticker is None:
    browse()
    ui.footer()
    st.stop()

if st.button("All stocks", icon=":material/arrow_back:", type="tertiary"):
    st.query_params.clear()
    st.rerun()

live = ui.quote(ticker)
series = ui.closes(ticker)
main, side = st.columns([2, 1], gap="large")

with main:
    st.markdown(f"<span class='muted'>{sectors[ticker]}</span>", unsafe_allow_html=True)
    heading, star = st.columns([5, 1], vertical_alignment="center")
    heading.header(f"{names[ticker]} ({ticker})", anchor=False)
    watching = ticker in storage.load_watchlist()
    if star.button("Watching" if watching else "Watch", icon=":material/star:" if watching else ":material/star_border:",
                   type="secondary", help="Show this stock in the watchlist on Home"):
        ui.toggle_watch(ticker)
        st.rerun()
    price = live.price if live else (float(series.iloc[-1]) if series is not None else None)
    previous = ui.previous_close(ticker, live.as_of.date() if live else None)
    if price is not None and previous:
        change = ui.change_html(price - previous, (price / previous - 1) * 100, "today")
    else:
        change = ""
    ui.hero("", ui.money(price), change)
    if live:
        st.caption(f"Price recorded {live.as_of:%b %d, %I:%M %p} New York time"
                   f"{' · may be about 15 minutes old' if live.market_open else ' · market closed'}.")
    else:
        st.caption("We couldn't get a current price, so this is the last saved close. Trading needs a "
                   "current price; try again in a minute.")

    history = storage.load_prices(ticker)

    @st.fragment
    def chart():
        if history is None or len(history) < 2:
            st.info("No price history saved for this stock yet.")
            return
        ranges, style, extras = st.columns([3, 1.4, 2.2], vertical_alignment="center")
        with ranges:
            choice = ui.range_picker(f"range-{ticker}")
        with style:
            kind = st.segmented_control("Chart", ["Line", "Candles"], default="Line", key=f"style-{ticker}",
                                        label_visibility="collapsed") or "Line"
        with extras:
            averages = st.pills("Averages", ["50-day average", "200-day average"], selection_mode="multi",
                                key=f"avg-{ticker}", label_visibility="collapsed")
        ui.stock_chart(history, ui.RANGES[choice], kind, averages)
        if averages:
            st.caption("A moving average is the average closing price over the last 50 or 200 trading days. "
                       "The AI uses how far the price is above or below them.")

    chart()

    if history is not None and len(history) > 1:
        year = history.iloc[-252:]
        st.markdown("**Key statistics**")
        cols = st.columns(4)
        ui.stat(cols[0], "52-week high", ui.money(year["high"].max()))
        ui.stat(cols[1], "52-week low", ui.money(year["low"].min()))
        ui.stat(cols[2], "Average volume (3 months)", f"{history['volume'].iloc[-63:].mean() / 1e6:,.1f}M shares")
        ui.stat(cols[3], "Change over 1 year", ui.percent(year["close"].iloc[-1] / year["close"].iloc[0] - 1, sign=True))

    st.subheader("AI suggestion")
    suggestion = pipeline.get_suggestion(ticker)
    if suggestion is None:
        reason = results.skipped.get(ticker) if results else None
        st.info(f"No suggestion for {ticker} today" + (f": {reason}." if reason else ".") + " You can still trade it.")
    else:
        with st.container(border=True):
            badge, chance = st.columns([1, 3], vertical_alignment="center")
            badge.markdown(f"### {ui.action_badge(suggestion.action)}")
            chance.progress(suggestion.probability_up,
                            text=f"**{ui.percent(suggestion.probability_up, 0)} chance** of being higher in 3 months")
            cols = st.columns(4)
            ui.stat(cols[0], "Confidence", suggestion.confidence.capitalize())
            ui.stat(cols[1], "Risk", suggestion.risk.capitalize())
            ui.stat(cols[2], "Track record", ui.percent(suggestion.track_record))
            ui.stat(cols[3], "Always guessing \"rise\"", ui.percent(suggestion.baseline))
            if suggestion.track_record is not None:
                st.caption(f"Track record: in past data this method got the direction right "
                           f"{ui.percent(suggestion.track_record)} of the time for {ticker}. Always guessing "
                           f"\"rise\" would have been right {ui.percent(suggestion.baseline)} of the time.")
            if not suggestion.beats_baseline:
                overall = results.backtest if results else None
                if overall is not None and overall.overall_track_record <= overall.overall_baseline:
                    st.caption("Overall, the method has not beaten always guessing \"rise\", "
                               "so every suggestion is Hold until it does.")
                else:
                    st.caption("The method has not beaten that baseline by at least 2 points for this stock, "
                               "so the suggestion is Hold.")
            st.markdown("**What pushed the chance up or down**")
            ui.contributions_chart(suggestion.contributions)
            with st.expander("See the numbers"):
                st.dataframe(pd.DataFrame([{
                    "Input": c.label,
                    "Value": round(c.value, 4),
                    "Effect (points)": round(c.effect, 2),
                } for c in suggestion.contributions]), hide_index=True, width="stretch")

        st.subheader("Jev's explanation")
        with st.container(border=True):
            with st.spinner("Asking Jev…"):
                explanation = pipeline.get_explanation(ticker)
            if explanation is None or explanation.status != "ok":
                st.info(explanation.reason if explanation else "No explanation available.",
                        icon=":material/info:")
            else:
                for icon, title, text in [
                    (":material/lightbulb:", "Why", explanation.why),
                    (":material/visibility:", "What stands out", explanation.stands_out),
                    (":material/warning:", "What could make it wrong", explanation.could_be_wrong),
                ]:
                    st.markdown(f"{icon} **{title}**")
                    st.write(text)

with side:
    cash, positions = account.cash_and_positions()
    position = positions.get(ticker)
    owned = position.shares if position else 0

    with st.container(border=True):
        st.markdown(f"**Trade {ticker}**")
        side_choice = st.segmented_control("Order", ["Buy", "Sell"], default="Buy", key=f"side-{ticker}",
                                           label_visibility="collapsed", width="stretch")
        side_choice = side_choice or "Buy"
        shares = st.number_input("Shares", min_value=1, step=1, value=1, key=f"shares-{ticker}")
        estimate = shares * price if price is not None else None
        rows = st.columns(2)
        rows[0].caption("Market price")
        rows[1].markdown(f"<div style='text-align:right'>{ui.money(price)}</div>", unsafe_allow_html=True)
        rows = st.columns(2)
        rows[0].caption("Estimated cost" if side_choice == "Buy" else "Estimated credit")
        rows[1].markdown(f"<div style='text-align:right'><b>{ui.money(estimate)}</b></div>", unsafe_allow_html=True)
        st.divider()
        if side_choice == "Buy":
            affordable = int(cash // price) if price else 0
            st.caption(f"{ui.money(cash)} buying power available · enough for up to {affordable} shares")
        else:
            st.caption(f"You own {owned} shares, so you can sell up to {owned}")

        @st.dialog("Review order")
        def review(kind: str, count: int):
            st.markdown(f"**{kind} {count} shares of {ticker}**")
            st.write(f"Estimated {'cost' if kind == 'Buy' else 'credit'}: {ui.money(count * price) if price else '—'}")
            st.caption("The order fills right away at the latest price when you place it, which may differ "
                       "slightly from the estimate. No fees.")
            place, cancel = st.columns(2)
            if place.button(f"Place {kind.lower()} order", type="primary", width="stretch"):
                try:
                    trade = account.buy(ticker, count) if kind == "Buy" else account.sell(ticker, count)
                except StockAIError as error:
                    st.error(error.message)
                    return
                ui.refresh_account()
                verb = "Bought" if kind == "Buy" else "Sold"
                st.session_state["order_done"] = f"{verb} {trade.shares} shares of {ticker} at {ui.money(trade.price)}."
                st.rerun()
            if cancel.button("Cancel", width="stretch"):
                st.rerun()

        if st.button(f"Review {side_choice.lower()} order", type="primary", width="stretch",
                     disabled=side_choice == "Sell" and owned == 0):
            review(side_choice, int(shares))

    if "order_done" in st.session_state:
        message = st.session_state.pop("order_done")
        st.toast(message, icon=":material/check_circle:")
        st.success(message, icon=":material/check_circle:")

    if position:
        value = owned * price if price is not None else None
        cost = position.cost
        with st.container(border=True):
            st.markdown("**Your position**")
            cols = st.columns(2)
            ui.stat(cols[0], "Shares", f"{owned}")
            ui.stat(cols[1], "Market value", ui.money(value))
            cols = st.columns(2)
            ui.stat(cols[0], "Average cost", ui.money(position.average_cost))
            if value is not None and cost:
                ui.stat(cols[1], "Total return", ui.change_html(value - cost, (value / cost - 1) * 100))

ui.footer()
