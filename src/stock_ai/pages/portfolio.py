import pandas as pd
import streamlit as st

from stock_ai import account, ui
from stock_ai.errors import StockAIError

ui.page("Portfolio")
ui.daily_results()
acct = ui.ensure_account()

try:
    portfolio, performance = ui.portfolio_and_performance()
except StockAIError as error:
    st.error(error.message)
    st.stop()

invested = portfolio.total_value - portfolio.cash
cols = st.columns(4)
cols[0].metric("Account value", ui.money(portfolio.total_value),
               f"{performance.account_gain_percent:+.2f}% since opening", border=True)
cols[1].metric("Same money in the S&P 500", ui.money(performance.benchmark_value),
               f"{performance.benchmark_gain_percent:+.2f}%", border=True)
cols[2].metric("You vs the market", f"{performance.ahead_by:+.2f} points",
               "ahead" if performance.ahead_by >= 0 else "behind",
               delta_color="normal" if performance.ahead_by >= 0 else "inverse", border=True)
cols[3].metric("Buying power", ui.money(portfolio.cash),
               f"{invested / portfolio.total_value * 100:.0f}% invested" if portfolio.total_value else None,
               delta_color="off", delta_arrow="off", border=True)
st.caption(f"Account opened {performance.since[:10]}. The S&P 500 comparison shows what the starting "
           f"{ui.money(acct.starting_cash)} would be worth in SPY, a fund that tracks the S&P 500.")

st.subheader("Holdings")
if portfolio.holdings:
    table = pd.DataFrame([{
        "Stock": h.ticker,
        "Company": h.company_name,
        "Last 30 days": list(ui.closes(h.ticker).iloc[-30:]) if ui.closes(h.ticker) is not None else [],
        "Shares": h.shares,
        "Average cost": h.average_cost,
        "Price": h.current_price,
        "Value": h.value,
        "Total return": h.gain,
        "Return %": h.gain_percent,
        "Share of account": h.value / portfolio.total_value * 100,
        "AI says": ui.action_text(h.suggestion),
    } for h in portfolio.holdings])

    def color(value):
        return f"color: {ui.GREEN}" if value > 0 else f"color: {ui.RED}" if value < 0 else ""

    event = st.dataframe(
        table.style.map(color, subset=["Total return", "Return %"]),
        hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
        column_config={
            "Last 30 days": st.column_config.LineChartColumn("Last 30 days", width="small"),
            "Average cost": st.column_config.NumberColumn(format="dollar"),
            "Price": st.column_config.NumberColumn(format="dollar"),
            "Value": st.column_config.NumberColumn(format="dollar"),
            "Total return": st.column_config.NumberColumn(format="dollar"),
            "Return %": st.column_config.NumberColumn(format="%+.2f%%"),
            "Share of account": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
        },
    )
    fallback = [h.ticker for h in portfolio.holdings if h.price_is_fallback]
    if fallback:
        st.caption(f"No current price for {', '.join(fallback)}, so the last closing price is used.")
    st.caption("Click a row to open the stock.")
    if event.selection.rows:
        ui.open_stock(table.iloc[event.selection.rows[0]]["Stock"])
else:
    with st.container(border=True):
        st.markdown("**No holdings yet.** Buy your first stock to see it here.")
        if st.button("Find a stock", icon=":material/search:"):
            st.switch_page("pages/stock.py")

st.subheader("Trade history")
trades = account.get_trades()
if trades:
    history = pd.DataFrame([{
        "When": pd.Timestamp(t.time).strftime("%b %d, %Y %I:%M %p"),
        "Stock": t.ticker,
        "Type": t.kind.capitalize(),
        "Shares": t.shares,
        "Price": t.price,
        "Total": t.shares * t.price if t.price is not None else None,
        "AI said at the time": ui.action_text(t.suggestion_at_time) if t.kind != "split" else "—",
    } for t in trades])
    picked = st.pills("Show", ["Buy", "Sell", "Split"], selection_mode="multi", label_visibility="collapsed")
    if picked:
        history = history[history["Type"].isin(picked)]
    st.dataframe(history, hide_index=True, width="stretch", column_config={
        "Price": st.column_config.NumberColumn(format="dollar"),
        "Total": st.column_config.NumberColumn(format="dollar"),
    })
else:
    st.caption("No trades yet.")

with st.expander("Start over", icon=":material/restart_alt:"):
    st.write(f"Resetting saves a copy of this account, then starts again with {ui.money(acct.starting_cash)}.")

    @st.dialog("Reset your account?")
    def confirm_reset():
        st.write(f"All holdings and trade history will be cleared and you'll start again with "
                 f"{ui.money(acct.starting_cash)}. A copy of the current account is saved first.")
        yes, no = st.columns(2)
        if yes.button("Reset account", type="primary", width="stretch"):
            try:
                account.reset()
            except StockAIError as error:
                st.error(error.message)
                return
            ui.refresh_account()
            st.rerun()
        if no.button("Cancel", width="stretch"):
            st.rerun()

    if st.button("Reset account…"):
        confirm_reset()

ui.footer()
