"""Pieces shared by the website's pages."""

from datetime import date

import streamlit as st

from stock_ai import account, pipeline, storage
from stock_ai.errors import StockAIError

DISCLAIMER = ("Suggestions are estimates from past prices, not guarantees. "
              "All money on this site is pretend.")
ACTION_LABELS = {"buy": "🟢 Buy", "hold": "⚪ Hold", "sell": "🔴 Sell", "": "—"}


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
    return results


def ensure_account():
    try:
        return account.open_account()
    except StockAIError as error:
        st.error(error.message)
        st.stop()


def open_stock(ticker: str):
    st.session_state["ticker"] = ticker
    st.switch_page("pages/stock.py")


def percent(value, digits=1, sign=False):
    if value is None:
        return "—"
    return f"{value * 100:+.{digits}f}%" if sign else f"{value * 100:.{digits}f}%"


def money(value):
    return f"${value:,.2f}"


def footer():
    st.divider()
    st.caption(DISCLAIMER)
