import pandas as pd
import streamlit as st

from stock_ai import account, autotrader, storage, ui
from stock_ai.errors import StockAIError

ui.page("AI trader")
results = ui.daily_results()

if storage.load_account(autotrader.OWNER) is None:
    st.info("The AI trader opens its account and places its first trades during the next daily update.",
            icon=":material/smart_toy:")
    ui.footer()
    st.stop()

try:
    portfolio, performance = ui.portfolio_and_performance(autotrader.OWNER)
    acct = account.open_account(autotrader.OWNER)
except StockAIError as error:
    st.error(error.message)
    st.stop()

main, side = st.columns([2, 1], gap="large")

with main:
    gain = performance.account_value - acct.starting_cash
    ui.hero("AI trader's account", ui.money(performance.account_value),
            ui.change_html(gain, performance.account_gain_percent, "since opening"))
    st.caption(f"Opened {performance.since[:10]} with {ui.money(acct.starting_cash)} of pretend cash. "
               f"The same money in the S&P 500 would be {ui.money(performance.benchmark_value)} "
               f"({performance.benchmark_gain_percent:+.2f}%).")

    choice = ui.range_picker("ai-range", options=("1W", "1M", "3M", "1Y", "All"), default="All")
    ai = ui.value_history_with_today(autotrader.OWNER, performance)
    lines = {"ai": ("AI trader", ui.ORANGE), "benchmark": ("S&P 500 (SPY)", ui.MUTED)}
    history = ai.rename(columns={"account": "ai"})
    if storage.load_account("you") is not None:
        _, yours = ui.portfolio_and_performance("you")
        you = ui.value_history_with_today("you", yours)[["time", "account"]]
        history = pd.concat([history, you], ignore_index=True).sort_values("time")
        lines = {"ai": ("AI trader", ui.ORANGE), "account": ("Your account", ui.BLUE),
                 "benchmark": ("S&P 500 (SPY)", ui.MUTED)}
    history = ui.last_days(history, choice)
    if history["ai"].notna().sum() < 3:
        st.info("The chart fills in after the market closes on the AI trader's first trading day.",
                icon=":material/show_chart:")
    else:
        ui.comparison_chart(history, lines)
    st.caption("The S&P 500 line is what the AI trader's starting cash would be worth in SPY.")

    st.subheader("What it owns")
    if portfolio.holdings:
        st.dataframe(pd.DataFrame([{
            "Stock": h.ticker,
            "Company": h.company_name,
            "Shares": h.shares,
            "Average cost": h.average_cost,
            "Price": h.current_price,
            "Value": h.value,
            "Total return": h.gain,
            "Return %": h.gain_percent,
        } for h in portfolio.holdings]), hide_index=True, width="stretch", column_config={
            "Average cost": st.column_config.NumberColumn(format="dollar"),
            "Price": st.column_config.NumberColumn(format="dollar"),
            "Value": st.column_config.NumberColumn(format="dollar"),
            "Total return": st.column_config.NumberColumn(format="dollar"),
            "Return %": st.column_config.NumberColumn(format="%+.2f%%"),
        })
    else:
        st.caption("Nothing right now. It buys when a stock reaches a 60% chance of rising.")

    st.subheader("Its trades")
    trades = account.get_trades(autotrader.OWNER)
    if trades:
        st.dataframe(pd.DataFrame([{
            "When": pd.Timestamp(t.time).strftime("%b %d, %Y %I:%M %p"),
            "Stock": t.ticker,
            "Type": t.kind.capitalize(),
            "Shares": t.shares,
            "Price": t.price,
            "Total": t.shares * t.price if t.price is not None else None,
        } for t in trades]), hide_index=True, width="stretch", column_config={
            "Price": st.column_config.NumberColumn(format="dollar"),
            "Total": st.column_config.NumberColumn(format="dollar"),
        })
    else:
        st.caption("No trades yet.")

with side:
    with st.container(border=True):
        st.markdown(":material/smart_toy: **How the AI trader works**")
        st.markdown(
            "- It trades **by itself** once a day, right after the daily update, in its own pretend account. "
            "Your account is never touched.\n"
            "- **Buys** a stock when the model gives it a **60% or higher** chance of rising in 3 months, "
            "putting about **5%** of its account into each one, best chances first.\n"
            "- **Sells** the whole holding when the chance falls to **40% or lower**. Otherwise it holds.\n"
            "- It follows the model **even though the model hasn't beaten guessing yet**, which is why it can "
            "buy stocks that show as Hold elsewhere on the site. This account shows whether following the "
            "model would really make money.")
    with st.container(border=True):
        ui.stat(st, "Cash", ui.money(portfolio.cash))
        ui.stat(st, "Stocks owned", f"{len(portfolio.holdings)}")
        ui.stat(st, "Vs the S&P 500", f"{performance.ahead_by:+.2f} points")
        last = storage.load_ai_last_run()
        if last:
            st.caption(f"Last traded on {last}.")
    if results is not None and results.suggestions:
        watch = sorted(results.suggestions, key=lambda s: s.probability_up, reverse=True)
        next_up = [s for s in watch if autotrader.rule_action(s) == "buy"][:5]
        with st.container(border=True):
            st.markdown("**At 60% or more today**")
            if not next_up:
                st.caption("No stock reached 60% today, so there was nothing to buy.")
            for s in next_up:
                st.progress(s.probability_up, text=f"{s.ticker} · {ui.percent(s.probability_up, 0)}")

    with st.expander("Start the AI trader over", icon=":material/restart_alt:"):
        st.write(f"Saves a copy of its account, then starts it again with {ui.money(acct.starting_cash)}. "
                 "It starts trading again with the next day's update.")

        @st.dialog("Reset the AI trader?")
        def confirm_reset():
            st.write("All of the AI trader's holdings and trades are cleared. A copy is saved first. "
                     "Your own account is not affected.")
            yes, no = st.columns(2)
            if yes.button("Reset AI trader", type="primary", width="stretch"):
                try:
                    account.reset(autotrader.OWNER)
                except StockAIError as error:
                    st.error(error.message)
                    return
                ui.refresh_account()
                st.rerun()
            if no.button("Cancel", width="stretch"):
                st.rerun()

        if st.button("Reset AI trader…"):
            confirm_reset()

ui.footer()
