import pandas as pd
import streamlit as st

from stock_ai import account, pipeline, storage, ui
from stock_ai.data import prices, universe
from stock_ai.errors import StockAIError

results = ui.daily_results()
ui.ensure_account()

sp500 = storage.load_sp500()
if sp500 is None:
    st.error("The S&P 500 list isn't available yet. Open the Home page to run the first update.")
    st.stop()
options = list(sp500["ticker"])
names = dict(zip(sp500["ticker"], sp500["company_name"]))
current = st.session_state.get("ticker")
if current and current not in names:
    st.warning(f"{current} isn't in the S&P 500. This site only trades S&P 500 stocks.")
    current = None
ticker = st.selectbox("Stock", options, index=options.index(current) if current else None,
                      format_func=lambda t: f"{t} · {names[t]}", placeholder="Search by ticker or name")
if ticker is None:
    st.stop()
st.session_state["ticker"] = ticker

st.title(f"{ticker} · {names[ticker]}")

try:
    quote = prices.get_latest_price(ticker)
    st.metric("Latest price", ui.money(quote.price))
    st.caption(f"Recorded {quote.as_of:%Y-%m-%d %H:%M} New York time"
               f"{' (market open, may be about 15 minutes old)' if quote.market_open else ' (market closed)'}.")
except StockAIError as error:
    quote = None
    st.warning(error.message)

history = storage.load_prices(ticker)
if history is not None:
    last_year = history["close"].iloc[-252:]
    st.line_chart(last_year.rename("Closing price"), height=260)

suggestion = pipeline.get_suggestion(ticker)
st.subheader("AI suggestion")
if suggestion is None:
    reason = results.skipped.get(ticker) if results else None
    st.info(f"No suggestion for {ticker} today" + (f": {reason}." if reason else ".") + " You can still trade it.")
else:
    cols = st.columns(4)
    cols[0].metric("Suggestion", ui.ACTION_LABELS[suggestion.action])
    cols[1].metric("Chance of rising in 3 months", ui.percent(suggestion.probability_up, 0))
    cols[2].metric("Confidence", suggestion.confidence.capitalize())
    cols[3].metric("Risk", suggestion.risk.capitalize())
    if suggestion.track_record is not None:
        st.write(f"**Track record:** in past data this method got the direction right "
                 f"{ui.percent(suggestion.track_record)} of the time for {ticker}. "
                 f"Always guessing \"rise\" would have been right {ui.percent(suggestion.baseline)} of the time.")
    if not suggestion.beats_baseline:
        st.caption("The method has not beaten that baseline for this stock, so the suggestion is Hold.")

    with st.expander("What pushed the chance up or down"):
        table = pd.DataFrame([{
            "Input": c.label,
            "Value": round(c.value, 4),
            "Effect (points)": round(c.effect, 2),
        } for c in suggestion.contributions])
        st.dataframe(table, hide_index=True, width="stretch")

    st.subheader("Jev's explanation")
    with st.spinner("Asking Jev…"):
        explanation = pipeline.get_explanation(ticker)
    if explanation is None or explanation.status != "ok":
        st.info(explanation.reason if explanation else "No explanation available.")
    else:
        st.markdown(f"**Why:** {explanation.why}")
        st.markdown(f"**What stands out:** {explanation.stands_out}")
        st.markdown(f"**What could make it wrong:** {explanation.could_be_wrong}")

st.subheader("Trade")
cash, positions = account.cash_and_positions()
owned = positions[ticker].shares if ticker in positions else 0
st.write(f"Cash: {ui.money(cash)} · You own {owned} shares of {ticker}.")
shares = st.number_input("Shares", min_value=1, step=1, value=1)
buy_col, sell_col = st.columns(2)
if buy_col.button("Buy", type="primary", width="stretch"):
    try:
        trade = account.buy(ticker, int(shares))
        st.success(f"Bought {trade.shares} shares of {ticker} at {ui.money(trade.price)}.")
    except StockAIError as error:
        st.error(error.message)
if sell_col.button("Sell", width="stretch"):
    try:
        trade = account.sell(ticker, int(shares))
        st.success(f"Sold {trade.shares} shares of {ticker} at {ui.money(trade.price)}.")
    except StockAIError as error:
        st.error(error.message)

ui.footer()
