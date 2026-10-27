import streamlit as st

from stock_ai import account, ui
from stock_ai.errors import StockAIError

st.title("📈 Stock AI paper trading")
results = ui.daily_results()
ui.ensure_account()

try:
    portfolio = account.get_portfolio()
    performance = account.get_performance(portfolio)
except StockAIError as error:
    st.error(error.message)
    st.stop()

left, middle, right = st.columns(3)
left.metric("Account value", ui.money(performance.account_value),
            f"{performance.account_gain_percent:+.2f}% since opening")
middle.metric("Same money in the S&P 500 (SPY)", ui.money(performance.benchmark_value),
              f"{performance.benchmark_gain_percent:+.2f}%")
right.metric("Cash", ui.money(portfolio.cash))
if performance.ahead_by >= 0:
    st.caption(f"You are {performance.ahead_by:.2f} points ahead of the market.")
else:
    st.caption(f"You are {-performance.ahead_by:.2f} points behind the market.")

st.subheader("Your stocks")
if portfolio.holdings:
    for holding in portfolio.holdings:
        cols = st.columns([2, 2, 2, 2, 1])
        cols[0].write(f"**{holding.ticker}** · {holding.company_name}")
        cols[1].write(f"{holding.shares} shares · {ui.money(holding.value)}")
        cols[2].write(f"{holding.gain_percent:+.1f}% ({ui.money(holding.gain)})")
        cols[3].write(ui.ACTION_LABELS.get(holding.suggestion, "—"))
        if cols[4].button("Open", key=f"own-{holding.ticker}"):
            ui.open_stock(holding.ticker)
else:
    st.info("You don't own any stocks yet. Search for one below or pick from today's suggestions.")

st.subheader("Find a stock")
with st.form("find", clear_on_submit=True, border=False):
    ticker = st.text_input("Ticker symbol, for example AAPL")
    if st.form_submit_button("Open") and ticker.strip():
        ui.open_stock(ticker.strip().upper())


def pick_list(title, picks):
    st.subheader(title)
    if not picks:
        st.write("Nothing stands out today.")
        return
    for pick in picks:
        cols = st.columns([3, 2, 2, 1])
        cols[0].write(f"**{pick.ticker}** · {pick.company_name}")
        cols[1].write(f"{ui.percent(pick.probability_up, 0)} likely to rise")
        cols[2].write(f"{pick.confidence.capitalize()} confidence · {pick.risk} risk")
        if cols[3].button("Open", key=f"{title}-{pick.ticker}"):
            ui.open_stock(pick.ticker)


if results is not None:
    st.caption(f"Suggestions from {results.date}, using prices up to "
               f"{results.suggestions[0].as_of if results.suggestions else '—'}. "
               f"{len(results.skipped)} stocks could not be scored today.")
    buys, sells = st.columns(2)
    with buys:
        pick_list("Top Buy suggestions", results.top_buys)
    with sells:
        pick_list("Top Sell suggestions", results.top_sells)

ui.footer()
