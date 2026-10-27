import pandas as pd
import streamlit as st

from stock_ai import account, ui
from stock_ai.errors import StockAIError

ui.daily_results()
acct = ui.ensure_account()
st.title("💼 Portfolio")

try:
    portfolio = account.get_portfolio()
    performance = account.get_performance(portfolio)
except StockAIError as error:
    st.error(error.message)
    st.stop()

cols = st.columns(3)
cols[0].metric("Account value", ui.money(portfolio.total_value), f"{performance.account_gain_percent:+.2f}%")
cols[1].metric("S&P 500 comparison", ui.money(performance.benchmark_value),
               f"{performance.benchmark_gain_percent:+.2f}%")
cols[2].metric("Cash", ui.money(portfolio.cash))
st.caption(f"Account opened {performance.since[:10]}. The comparison shows what the starting "
           f"{ui.money(acct.starting_cash)} would be worth in SPY, a fund that tracks the S&P 500.")

st.subheader("Holdings")
if portfolio.holdings:
    st.dataframe(pd.DataFrame([{
        "Stock": h.ticker,
        "Company": h.company_name,
        "Shares": h.shares,
        "Average cost": ui.money(h.average_cost),
        "Price": ui.money(h.current_price) + (" (last close)" if h.price_is_fallback else ""),
        "Value": ui.money(h.value),
        "Gain": f"{ui.money(h.gain)} ({h.gain_percent:+.1f}%)",
        "AI says": ui.ACTION_LABELS.get(h.suggestion, "—"),
    } for h in portfolio.holdings]), hide_index=True, width="stretch")
else:
    st.info("No holdings yet.")

st.subheader("Trade history")
trades = account.get_trades()
if trades:
    st.dataframe(pd.DataFrame([{
        "When": t.time[:16].replace("T", " "),
        "Stock": t.ticker,
        "Type": t.kind.capitalize(),
        "Shares": t.shares,
        "Price": ui.money(t.price) if t.price is not None else "—",
        "AI said at the time": ui.ACTION_LABELS.get(t.suggestion_at_time, "—") if t.kind != "split" else "—",
    } for t in trades]), hide_index=True, width="stretch")
else:
    st.write("No trades yet.")

st.subheader("Start over")
st.write(f"Resetting saves a copy of this account, then starts again with {ui.money(acct.starting_cash)}.")
confirm = st.checkbox("I want to reset my account")
if st.button("Reset account", disabled=not confirm):
    try:
        account.reset()
        st.success("Your account has been reset.")
        st.rerun()
    except StockAIError as error:
        st.error(error.message)

ui.footer()
