"""The website. Start it from the project root with:

    .venv/bin/streamlit run src/stock_ai/app.py
"""

import streamlit as st

st.set_page_config(page_title="Stock AI paper trading", page_icon="📈", layout="wide")

navigation = st.navigation([
    st.Page("pages/home.py", title="Home", icon=":material/home:", default=True),
    st.Page("pages/stock.py", title="Stocks", icon=":material/candlestick_chart:"),
    st.Page("pages/portfolio.py", title="Portfolio", icon=":material/account_balance_wallet:"),
    st.Page("pages/ai_trader.py", title="AI trader", icon=":material/smart_toy:"),
    st.Page("pages/scorecard.py", title="Scorecard", icon=":material/target:"),
], position="top")
navigation.run()
