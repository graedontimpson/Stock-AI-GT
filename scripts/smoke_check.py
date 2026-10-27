"""Check that the outside services answer in the shape the data plan expects.

Contacts Wikipedia, Yahoo Finance, and FRED once each. Pass --claude to also
send one small request to Claude, which uses a tiny amount of API credit.

Run from the project root:
    .venv/bin/python scripts/smoke_check.py
    .venv/bin/python scripts/smoke_check.py --claude
"""

import io
import sys
from datetime import date, timedelta

import pandas as pd
import requests

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={code}"
FRED_CODES = ["DFF", "CPIAUCSL", "UNRATE", "VIXCLS"]
# Wikipedia asks for a descriptive User-Agent. FRED refuses custom ones and
# only answers the library's default, so FRED requests send no HEADERS.
HEADERS = {"User-Agent": "stock-ai-smoke-check/0.1 (personal project)"}

results = []


def check(name):
    """Run a check function, record whether it passed, and keep going either way."""
    def wrap(fn):
        try:
            detail = fn()
            results.append((name, True, detail))
        except Exception as error:  # report every failure, then move on
            results.append((name, False, f"{type(error).__name__}: {error}"))
        return fn
    return wrap


@check("Wikipedia: S&P 500 table")
def wikipedia():
    response = requests.get(WIKIPEDIA_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    table = pd.read_html(io.StringIO(response.text))[0]
    expected = {"Symbol", "Security", "GICS Sector"}
    missing = expected - set(table.columns)
    assert not missing, f"missing columns {missing}; got {list(table.columns)}"
    assert 490 <= len(table) <= 510, f"{len(table)} rows"
    dotted = [t for t in table["Symbol"] if "." in t]
    return f"{len(table)} rows; tickers with a dot: {dotted}"


@check("Yahoo Finance: 1 month of history for AAPL and SPY")
def yahoo_history():
    import yfinance as yf
    data = yf.download(["AAPL", "SPY"], period="1mo", auto_adjust=False,
                       progress=False, group_by="ticker")
    for ticker in ["AAPL", "SPY"]:
        columns = set(data[ticker].columns)
        expected = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
        assert expected <= columns, f"{ticker} columns {columns}"
        assert len(data[ticker].dropna()) >= 15, f"{ticker}: {len(data[ticker])} rows"
    return f"{len(data)} rows; columns per ticker: {sorted(data['AAPL'].columns)}"


@check("Yahoo Finance: latest price for AAPL")
def yahoo_latest():
    import yfinance as yf
    info = yf.Ticker("AAPL").fast_info
    price = info["lastPrice"]
    assert price and price > 0, f"price {price}"
    history = yf.Ticker("AAPL").history(period="1d", interval="1m")
    as_of = history.index[-1] if len(history) else "no intraday data"
    return f"price {price:.2f}; latest minute recorded {as_of}"


@check("Yahoo Finance: split records for AAPL")
def yahoo_splits():
    import yfinance as yf
    splits = yf.Ticker("AAPL").splits
    assert len(splits) > 0, "no splits returned"
    recent = splits[splits.index >= pd.Timestamp("2020-01-01", tz=splits.index.tz)]
    return f"{len(splits)} splits; since 2020: {recent.to_dict()}"


for code in FRED_CODES:
    @check(f"FRED: {code}")
    def fred(code=code):
        response = requests.get(FRED_URL.format(code=code), timeout=30)
        response.raise_for_status()
        table = pd.read_csv(io.StringIO(response.text))
        assert len(table.columns) == 2, f"columns {list(table.columns)}"
        dates = pd.to_datetime(table.iloc[:, 0])
        values = pd.to_numeric(table.iloc[:, 1], errors="coerce")
        latest = table.iloc[values.last_valid_index()]
        missing = int(values.isna().sum())
        assert dates.max() > pd.Timestamp(date.today() - timedelta(days=120)), "data is stale"
        return (f"columns {list(table.columns)}; {len(table)} rows from {dates.min().date()}; "
                f"latest {latest.iloc[0]} = {latest.iloc[1]}; non-numeric values: {missing}")


if "--claude" in sys.argv:
    @check("Claude: one small request")
    def claude():
        import os
        import anthropic
        from dotenv import load_dotenv
        load_dotenv()
        assert os.getenv("ANTHROPIC_API_KEY"), "ANTHROPIC_API_KEY is not set in .env"
        model = os.getenv("JEV_MODEL", "claude-opus-5-5")
        client = anthropic.Anthropic()
        reply = client.messages.create(
            model=model,
            max_tokens=20,
            messages=[{"role": "user", "content": "Reply with the single word: ready"}],
        )
        text = "".join(block.text for block in reply.content if block.type == "text")
        return f"model {model} replied: {text.strip()!r}"


for name, passed, detail in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name}\n      {detail}")
failed = sum(1 for _, passed, _ in results if not passed)
print(f"\n{len(results) - failed} passed, {failed} failed")
sys.exit(1 if failed else 0)
