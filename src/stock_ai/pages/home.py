import streamlit as st

from stock_ai import autotrader, storage, ui
from stock_ai.errors import StockAIError

ui.page("Home")
results = ui.daily_results()
acct = ui.ensure_account()

try:
    portfolio, performance = ui.portfolio_and_performance()
except StockAIError as error:
    st.error(error.message)
    st.stop()

main, side = st.columns([2, 1], gap="large")

with main:
    gain = performance.account_value - acct.starting_cash
    ui.hero("Your account", ui.money(performance.account_value),
            ui.change_html(gain, performance.account_gain_percent, "since opening"))
    behind = "ahead of" if performance.ahead_by >= 0 else "behind"
    st.caption(f"The same {ui.money(acct.starting_cash)} in the S&P 500 would be worth "
               f"{ui.money(performance.benchmark_value)} ({performance.benchmark_gain_percent:+.2f}%). "
               f"You are {abs(performance.ahead_by):.2f} points {behind} the market.")

    choice = ui.range_picker("home-range", options=("1W", "1M", "3M", "1Y", "All"), default="All")
    history = ui.last_days(ui.value_history_with_today("you", performance), choice)
    if len(history) < 3:
        st.info("Your account chart fills in after the market closes on the first trading day "
                "after you opened the account.", icon=":material/show_chart:")
    else:
        ui.comparison_chart(history)

    st.subheader("Today's AI picks")
    if results is None:
        st.info("Suggestions appear after the first daily update finishes.")
    elif not results.top_buys and not results.top_sells:
        with st.container(border=True):
            st.markdown("**Nothing stands out today.** Every stock is a :gray-badge[:material/pause: Hold].")
            backtest = results.backtest
            if backtest is not None and backtest.overall_track_record <= backtest.overall_baseline:
                st.caption(f"In testing on past data, the AI was right {ui.percent(backtest.overall_track_record)} "
                           f"of the time, while always guessing \"rise\" was right "
                           f"{ui.percent(backtest.overall_baseline)} of the time. Until it beats that, "
                           "it won't suggest Buy or Sell.")
            if st.button("See the scorecard", icon=":material/target:"):
                st.switch_page("pages/scorecard.py")
    else:
        buys, sells = st.columns(2)
        for column, title, picks in [(buys, "Top Buys", results.top_buys), (sells, "Top Sells", results.top_sells)]:
            with column:
                st.markdown(f"**{title}**")
                if not picks:
                    st.caption("Nothing stands out today.")
                for pick in picks:
                    with st.container(border=True):
                        top, button = st.columns([4, 1], vertical_alignment="center")
                        top.markdown(f"**{pick.ticker}** {ui.action_badge(pick.action)}  \n"
                                     f"<span class='muted'>{pick.company_name}</span>", unsafe_allow_html=True)
                        if button.button("Open", key=f"{title}-{pick.ticker}", type="tertiary"):
                            ui.open_stock(pick.ticker)
                        st.progress(pick.probability_up,
                                    text=f"{ui.percent(pick.probability_up, 0)} chance of rising in 3 months · "
                                         f"{pick.confidence} confidence · {pick.risk} risk")
    if results is not None:
        as_of = results.suggestions[0].as_of if results.suggestions else "—"
        st.caption(f"Suggestions from {results.date}, using prices up to {as_of}. "
                   f"{len(results.skipped)} stocks could not be scored.")

with side:
    with st.container(border=True):
        ui.stat(st, "Buying power", ui.money(portfolio.cash))
        if st.button("Find a stock to trade", icon=":material/search:", width="stretch"):
            st.switch_page("pages/stock.py")

    if storage.load_account(autotrader.OWNER) is not None:
        with st.container(border=True):
            _, ai = ui.portfolio_and_performance(autotrader.OWNER)
            ui.stat(st, ":material/smart_toy: AI trader", ui.money(ai.account_value))
            st.markdown(ui.change_html(ai.account_value - acct.starting_cash, ai.account_gain_percent,
                                       "since opening"), unsafe_allow_html=True)
            if st.button("See what the AI is trading", width="stretch"):
                st.switch_page("pages/ai_trader.py")

    with st.container(border=True):
        st.markdown("**Your stocks**")
        if not portfolio.holdings:
            st.caption("You don't own any stocks yet. Search above, or open one of today's picks.")
        for holding in portfolio.holdings:
            name, chart, price = st.columns([2, 2, 2], vertical_alignment="center")
            if name.button(holding.ticker, key=f"own-{holding.ticker}", type="tertiary"):
                ui.open_stock(holding.ticker)
            name.caption(f"{holding.shares} shares")
            series = ui.closes(holding.ticker)
            if series is not None and len(series) > 1:
                with chart:
                    ui.sparkline(series.iloc[-30:])
            price.markdown(f"**{ui.money(holding.current_price)}**  \n"
                           f"<span class='{ui.direction(holding.gain)}'>{holding.gain_percent:+.2f}%</span>"
                           f"<span class='muted'> total</span>",
                           unsafe_allow_html=True)

ui.footer()
