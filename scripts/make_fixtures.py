"""Create the made-up test data in tests/fixtures/. Running it again gives identical files.

    .venv/bin/python scripts/make_fixtures.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
START, END = "2022-01-03", "2024-12-31"


def price_table(rng, days, start_price, drift, volatility):
    returns = rng.normal(drift, volatility, len(days))
    adj_close = start_price * np.exp(np.cumsum(returns))
    close = adj_close * 1.01  # pretend dividends make the adjusted price a little lower
    table = pd.DataFrame({
        "open": close * (1 + rng.normal(0, 0.002, len(days))),
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "adj_close": adj_close,
        "volume": rng.integers(1_000_000, 5_000_000, len(days)).astype(float),
    }, index=days)
    table.index.name = "date"
    return table.round(4)


def main():
    rng = np.random.default_rng(7)
    days = pd.bdate_range(START, END)
    (FIXTURES / "prices").mkdir(parents=True, exist_ok=True)

    tables = {
        "SPY": price_table(rng, days, 400, 0.0003, 0.010),
        "AAA": price_table(rng, days, 100, 0.0005, 0.015),  # clean
        "BBB": price_table(rng, days, 50, 0.0001, 0.020),
        "CCC": price_table(rng, days, 30, 0.0002, 0.025),
        "DDD": price_table(rng, days, 80, 0.0002, 0.015),
    }
    tables["BBB"] = tables["BBB"].drop(days[300])  # one missing day: filled in
    tables["CCC"] = tables["CCC"].drop(days[400:408])  # an 8-day gap: skipped
    tables["DDD"].iloc[500, tables["DDD"].columns.get_loc("close")] = 0.0  # a zero price: skipped
    for ticker, table in tables.items():
        table.to_csv(FIXTURES / "prices" / f"{ticker}.csv")

    pd.DataFrame({
        "ticker": ["AAA", "BBB", "CCC", "DDD"],
        "company_name": ["Alpha Corp", "Beta Inc.", "Gamma Co", "Delta Ltd"],
        "sector": ["Information Technology", "Health Care", "Energy", "Financials"],
        "downloaded": "2024-12-31T17:00:00",
    }).to_csv(FIXTURES / "sp500.csv", index=False)

    # Economic series in FRED's own CSV format, with missing values.
    calendar_days = pd.date_range("2020-01-01", END, freq="D")
    dff = pd.Series(np.round(np.linspace(0.1, 5.3, len(calendar_days)), 2), index=calendar_days)
    vix = pd.Series(np.round(20 + rng.normal(0, 3, len(calendar_days)), 2), index=calendar_days)
    vix[vix.index.dayofweek >= 5] = np.nan  # no VIX at weekends
    months = pd.date_range("2020-01-01", "2024-11-01", freq="MS")
    cpi = pd.Series(np.round(258 * 1.003 ** np.arange(len(months)), 3), index=months)
    unrate = pd.Series(np.round(4 + np.sin(np.arange(len(months)) / 6), 1), index=months)
    unrate[pd.Timestamp("2023-10-01")] = np.nan  # a month that was never published
    (FIXTURES / "fred").mkdir(exist_ok=True)
    for code, series in {"DFF": dff, "VIXCLS": vix, "CPIAUCSL": cpi, "UNRATE": unrate}.items():
        text = "observation_date," + code + "\n" + "".join(
            f"{day.date()},{'' if pd.isna(value) else value}\n" for day, value in series.items())
        (FIXTURES / "fred" / f"{code}.csv").write_text(text)

    replies = {
        "good": {
            "why": "The model gives this stock a 66% chance of rising.",
            "stands_out": "The price is well above its 200-day average.",
            "could_be_wrong": "The track record is only a little above the baseline.",
        },
        "missing_field": {"why": "Only one field."},
        "extra_field": {"why": "a", "stands_out": "b", "could_be_wrong": "c", "advice": "buy now"},
    }
    (FIXTURES / "jev_replies.json").write_text(json.dumps(replies, indent=2) + "\n")
    print(f"Fixtures written to {FIXTURES}")


if __name__ == "__main__":
    main()
