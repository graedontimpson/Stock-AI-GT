import pandas as pd
import streamlit as st

from stock_ai import scorecard, ui

ui.page("Scorecard")
ui.daily_results()
st.write("How the AI's suggestions have turned out. Each Buy and Sell suggestion is checked "
         "3 months after it was made: a Buy is right if the price rose, a Sell if it fell.")

card = scorecard.get_scorecard()

st.subheader("Real results")
if card.buy_total + card.sell_total == 0:
    when = f" The first results are due around **{card.first_due}**." if card.first_due else ""
    with st.container(border=True):
        st.markdown(f":material/hourglass_top: No suggestion is 3 months old yet. "
                    f"**{card.pending}** are waiting to be checked.{when}")
else:
    cols = st.columns(3)
    cols[0].metric("Buy suggestions right", f"{card.buy_right} of {card.buy_total}", border=True)
    cols[1].metric("Sell suggestions right", f"{card.sell_right} of {card.sell_total}", border=True)
    cols[2].metric("Waiting to be checked", card.pending, border=True)
    cols = st.columns(3)
    cols[0].metric("Buy picks, average 3-month change", ui.percent(card.avg_buy_change, sign=True), border=True)
    cols[1].metric("Sell picks, average 3-month change", ui.percent(card.avg_sell_change, sign=True), border=True)
    cols[2].metric("S&P 500 (SPY), same periods", ui.percent(card.avg_spy_change, sign=True), border=True)
    st.caption("Following the suggestions beat the market if Buy picks did better than SPY and Sell picks did worse.")
    st.dataframe(pd.DataFrame([
        {"Confidence": level.capitalize(), "Right": v["right"], "Checked": v["total"]}
        for level, v in card.by_confidence.items()
    ]), hide_index=True)

st.subheader("Backtest")
backtest = card.backtest
if backtest is None:
    st.info("The backtest hasn't run yet.")
else:
    edge = (backtest.overall_track_record - backtest.overall_baseline) * 100
    cols = st.columns(3)
    cols[0].metric("AI got the direction right", ui.percent(backtest.overall_track_record),
                   f"{edge:+.1f} points vs guessing", border=True)
    cols[1].metric("Always guessing \"rise\"", ui.percent(backtest.overall_baseline), border=True)
    cols[2].metric("Forecasts tested", f"{backtest.overall_forecasts:,}",
                   f"{backtest.tested_from} to {backtest.tested_to}", delta_color="off", delta_arrow="off",
                   border=True)
    if backtest.overall_track_record <= backtest.overall_baseline:
        st.warning("Overall, the method has not beaten always guessing \"rise\". "
                   "Treat its suggestions with that in mind.", icon=":material/warning:")
    st.caption("The backtest trains only on companies in the S&P 500 today, which leaves out ones "
               "that dropped out or failed. That makes the past look a little easier to predict "
               "than it really was. It was last run on " + backtest.run_date + ".")
    if backtest.calibration:
        st.markdown("**Do the probabilities mean what they say?** When the method gave a stock a "
                    "certain chance of rising, this is how often it really rose:")
        st.dataframe(pd.DataFrame([{
            "Chance given": b["bucket"],
            "Forecasts": b["forecasts"],
            "Actually rose": b["rose_share"] * 100,
        } for b in backtest.calibration]), hide_index=True, column_config={
            "Actually rose": st.column_config.ProgressColumn(format="%.1f%%", min_value=0, max_value=100),
        })

ui.footer()
