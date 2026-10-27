import pandas as pd
import streamlit as st

from stock_ai import scorecard, ui

ui.daily_results()
st.title("🎯 Scorecard")
st.write("How the AI's suggestions have turned out. Each Buy and Sell suggestion is checked "
         "3 months after it was made: a Buy is right if the price rose, a Sell if it fell.")

card = scorecard.get_scorecard()

st.subheader("Real results")
if card.buy_total + card.sell_total == 0:
    when = f" The first results are due around {card.first_due}." if card.first_due else ""
    st.info(f"No suggestion is 3 months old yet. {card.pending} are waiting to be checked.{when}")
else:
    cols = st.columns(3)
    cols[0].metric("Buy suggestions right", f"{card.buy_right} of {card.buy_total}")
    cols[1].metric("Sell suggestions right", f"{card.sell_right} of {card.sell_total}")
    cols[2].metric("Waiting to be checked", card.pending)
    st.write(
        f"Over the same 3-month periods, Buy picks changed {ui.percent(card.avg_buy_change, sign=True)} on average, "
        f"Sell picks {ui.percent(card.avg_sell_change, sign=True)}, and the S&P 500 (SPY) "
        f"{ui.percent(card.avg_spy_change, sign=True)}. Following the suggestions beat the market "
        "if Buy picks did better than SPY and Sell picks did worse."
    )
    st.dataframe(pd.DataFrame([
        {"Confidence": level.capitalize(), "Right": v["right"], "Checked": v["total"]}
        for level, v in card.by_confidence.items()
    ]), hide_index=True)

st.subheader("Backtest")
backtest = card.backtest
if backtest is None:
    st.info("The backtest hasn't run yet.")
else:
    st.write(
        f"Tested on past data from {backtest.tested_from} to {backtest.tested_to} "
        f"({backtest.overall_forecasts:,} forecasts). The method got the direction right "
        f"**{ui.percent(backtest.overall_track_record)}** of the time. Always guessing \"rise\" "
        f"would have been right **{ui.percent(backtest.overall_baseline)}** of the time."
    )
    if backtest.overall_track_record <= backtest.overall_baseline:
        st.warning("Overall, the method has not beaten always guessing \"rise\". "
                   "Treat its suggestions with that in mind.")
    st.caption("The backtest trains only on companies in the S&P 500 today, which leaves out ones "
               "that dropped out or failed. That makes the past look a little easier to predict "
               "than it really was. It was last run on " + backtest.run_date + ".")
    if backtest.calibration:
        st.write("**Do the probabilities mean what they say?** When the method gave a stock a "
                 "certain chance of rising, this is how often it really rose:")
        st.dataframe(pd.DataFrame([{
            "Chance given": b["bucket"],
            "Forecasts": b["forecasts"],
            "Actually rose": ui.percent(b["rose_share"]),
        } for b in backtest.calibration]), hide_index=True)

ui.footer()
