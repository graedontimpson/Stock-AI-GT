"""The model's inputs, built only from information available on each day.

Formulas are in 04_data/output.md section 4.
"""

import math

import numpy as np
import pandas as pd

from stock_ai.errors import NotEnoughHistoryError

DAYS_1M, DAYS_3M, DAYS_6M, DAYS_1Y = 21, 63, 126, 252
MONTHLY_DELAY_MONTHS = 2  # a month's figure is used from the 1st of the month after next

FEATURES = [
    "change_1m", "change_3m", "change_6m",
    "vs_avg_50", "vs_avg_200",
    "volatility_3m", "volume_ratio",
    "market_change_1m", "market_change_3m", "vs_market_3m",
    "interest_rate", "interest_rate_change_3m",
    "inflation", "unemployment", "vix",
]

LABELS = {
    "change_1m": "Price change over 1 month",
    "change_3m": "Price change over 3 months",
    "change_6m": "Price change over 6 months",
    "vs_avg_50": "Price compared with 50-day average",
    "vs_avg_200": "Price compared with 200-day average",
    "volatility_3m": "Volatility over 3 months",
    "volume_ratio": "Trading volume compared with usual",
    "market_change_1m": "Market change over 1 month",
    "market_change_3m": "Market change over 3 months",
    "vs_market_3m": "3-month change compared with the market",
    "interest_rate": "Interest rate",
    "interest_rate_change_3m": "Interest rate change over 3 months",
    "inflation": "Inflation rate",
    "unemployment": "Unemployment rate",
    "vix": "Market nervousness index (VIX)",
}


def _asof(calendar: pd.DatetimeIndex, series: pd.Series, exact: bool) -> pd.Series:
    """For each calendar day, the latest value dated on or before it (or strictly
    before it when exact=False)."""
    left = pd.DataFrame({"date": calendar.astype("datetime64[ns]")})
    right = series.dropna().rename("value").rename_axis("date").reset_index()
    right["date"] = right["date"].astype("datetime64[ns]")
    merged = pd.merge_asof(left, right.sort_values("date"), on="date", allow_exact_matches=exact)
    return pd.Series(merged["value"].to_numpy(), index=calendar)


def _monthly_available(series: pd.Series) -> pd.Series:
    """Re-date a monthly series to the first day it may be used."""
    available = series.copy()
    available.index = series.index + pd.DateOffset(months=MONTHLY_DELAY_MONTHS)
    return available


def point_in_time_economy(economy: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    cpi = economy["CPIAUCSL"].dropna()
    months = pd.date_range(cpi.index.min(), cpi.index.max(), freq="MS")
    cpi = cpi.reindex(months)  # a missing month stays missing, so shift(12) lines up by month
    inflation = (cpi / cpi.shift(12) - 1) * 100
    table = pd.DataFrame(index=calendar)
    table["interest_rate"] = _asof(calendar, economy["DFF"], exact=False)
    table["vix"] = _asof(calendar, economy["VIXCLS"], exact=True)
    table["inflation"] = _asof(calendar, _monthly_available(inflation.dropna()), exact=True)
    table["unemployment"] = _asof(calendar, _monthly_available(economy["UNRATE"].dropna()), exact=True)
    table["interest_rate_change_3m"] = table["interest_rate"] - table["interest_rate"].shift(DAYS_3M)
    return table


def market_signals(market: pd.DataFrame) -> pd.DataFrame:
    m = market["adj_close"]
    return pd.DataFrame({
        "market_change_1m": m / m.shift(DAYS_1M) - 1,
        "market_change_3m": m / m.shift(DAYS_3M) - 1,
    })


def build_signals(prices: pd.DataFrame, market: pd.DataFrame, economy: pd.DataFrame,
                  ticker: str = "", context: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per trading day with every signal. Days missing any signal are left out.

    `context` is the market and economy signals on SPY's calendar; pass it when
    building many stocks so it is worked out once.
    """
    if len(prices) < DAYS_1Y:
        raise NotEnoughHistoryError(ticker or "This stock")
    if context is None:
        context = build_context(market, economy)

    p = prices["adj_close"]
    volume = prices["volume"]
    table = pd.DataFrame(index=prices.index)
    table["change_1m"] = p / p.shift(DAYS_1M) - 1
    table["change_3m"] = p / p.shift(DAYS_3M) - 1
    table["change_6m"] = p / p.shift(DAYS_6M) - 1
    table["vs_avg_50"] = p / p.rolling(50).mean() - 1
    table["vs_avg_200"] = p / p.rolling(200).mean() - 1
    table["volatility_3m"] = p.pct_change().rolling(DAYS_3M).std() * math.sqrt(DAYS_1Y)
    table["volume_ratio"] = (volume.rolling(DAYS_1M).mean() / volume.rolling(DAYS_1Y).mean()).replace(
        [np.inf, -np.inf], np.nan)
    table = table.join(context.reindex(prices.index))
    table["vs_market_3m"] = table["change_3m"] - table["market_change_3m"]
    table = table[FEATURES].dropna()
    table.insert(0, "ticker", ticker)
    table.index.name = "date"
    if table.empty:
        raise NotEnoughHistoryError(ticker or "This stock")
    return table


def build_context(market: pd.DataFrame, economy: pd.DataFrame) -> pd.DataFrame:
    return market_signals(market).join(point_in_time_economy(economy, market.index))


def add_outcomes(signals: pd.DataFrame, prices: pd.DataFrame, horizon: int = DAYS_3M) -> pd.DataFrame:
    """Add `rose`: 1 if the adjusted close `horizon` trading days later is higher,
    0 if not, and empty where that day has not happened yet."""
    p = prices["adj_close"]
    future = p.shift(-horizon)
    rose = (future > p).astype(float).where(future.notna())
    result = signals.copy()
    result["rose"] = rose.reindex(signals.index)
    return result
