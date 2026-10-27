"""The website. Start it from the project root with:

    .venv/bin/streamlit run src/stock_ai/app.py
"""

import streamlit as st

st.set_page_config(page_title="Stock AI paper trading", page_icon="📈", layout="wide")

navigation = st.navigation([
    st.Page("pages/home.py", title="Home", icon="🏠", default=True),
    st.Page("pages/stock.py", title="Stock", icon="🔎"),
    st.Page("pages/portfolio.py", title="Portfolio", icon="💼"),
    st.Page("pages/scorecard.py", title="Scorecard", icon="🎯"),
])
navigation.run()
