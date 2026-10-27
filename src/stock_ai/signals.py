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
    "revenue_growth": "Revenue growth over a year",
    "earnings_growth": "Profit growth over a year",
    "profit_margin": "Profit margin",
    "pe_ratio": "Price compared with profit (P/E)",
    "debt_to_equity": "Debt compared with equity",
    "earnings_surprise": "Last earnings surprise",
    "days_since_earnings": "Trading days since last earnings",
    "financials_missing": "Some company figures were missing",
}

# Phase 2: company inputs. Formulas in 06_phase2/output.md section 4.
COMPANY_FEATURES = [
    "revenue_growth", "earnings_growth", "profit_margin", "pe_ratio",
    "debt_to_equity", "earnings_surprise", "days_since_earnings",
]
ALL_FEATURES = FEATURES + COMPANY_FEATURES + ["financials_missing"]

# Extreme values (a P/E of 5,000, profit up 80 times) would swamp the model, so each
# company input is limited to a sensible range.
COMPANY_LIMITS = {
    "revenue_growth": (-1, 3),
    "earnings_growth": (-5, 5),
    "profit_margin": (-1, 1),
    "pe_ratio": (0, 200),
    "debt_to_equity": (0, 20),
    "earnings_surprise": (-100, 100),
    "days_since_earnings": (0, 130),
}
QUARTER_GAP_DAYS = (75, 105)


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


# Phase 2: company inputs

def _known_values(table: pd.DataFrame, concept: str, as_of: pd.Timestamp) -> pd.Series:
    """Each period's latest value filed on or before `as_of`, by period end."""
    rows = table[(table["concept"] == concept) & (table["filed"] <= as_of)]
    rows = rows.sort_values("filed").drop_duplicates("period_end", keep="last")
    return rows.set_index("period_end")["value"].sort_index()


def _consecutive(quarters: pd.Series, count: int) -> pd.Series | None:
    """The last `count` quarters, if they follow on from each other without gaps."""
    if len(quarters) < count:
        return None
    last = quarters.iloc[-count:]
    gaps = last.index.to_series().diff().dt.days.dropna()
    if not gaps.between(*QUARTER_GAP_DAYS).all():
        return None
    return last


def financial_state(financials: pd.DataFrame) -> pd.DataFrame:
    """What was known about the company after each filing date, one row per date."""
    rows = []
    for filed in sorted(financials["filed"].unique()):
        filed = pd.Timestamp(filed)
        state = {"filed": filed}
        for concept in ("revenue", "net_income", "eps_diluted"):
            eight = _consecutive(_known_values(financials, concept, filed), 8)
            four = _consecutive(_known_values(financials, concept, filed), 4)
            state[f"{concept}_ttm"] = four.sum() if four is not None else np.nan
            state[f"{concept}_prior"] = eight.iloc[:4].sum() if eight is not None else np.nan
        for concept in ("liabilities", "equity"):
            known = _known_values(financials, concept, filed)
            state[concept] = known.iloc[-1] if len(known) else np.nan
        rows.append(state)
    return pd.DataFrame(rows).set_index("filed") if rows else pd.DataFrame()


def split_factor(splits: pd.DataFrame | None, calendar: pd.DatetimeIndex) -> pd.Series:
    """For each day, the combined ratio of all later splits. Saved prices are adjusted
    for every split up to today, so multiplying by this gives the price as it really
    was that day, which is what a filed earnings-per-share figure is comparable with."""
    factor = pd.Series(1.0, index=calendar)
    if splits is None:
        return factor
    for row in splits.itertuples():
        factor[calendar < row.date] *= row.ratio
    return factor


def company_signals(prices: pd.DataFrame, financials: pd.DataFrame | None,
                    earnings: pd.DataFrame | None, splits: pd.DataFrame | None = None) -> pd.DataFrame:
    """The 7 company inputs for each trading day; empty where not known yet.

    A filing is used from the trading day after it was filed, and an earnings
    announcement from the trading day after it was made."""
    calendar = prices.index
    table = pd.DataFrame(index=calendar, columns=COMPANY_FEATURES, dtype=float)

    if financials is not None and not financials.empty:
        state = financial_state(financials)
        known = pd.DataFrame(index=calendar)
        for column in state.columns:
            known[column] = _asof(calendar, state[column], exact=False)
        positive = lambda x: x.where(x > 0)
        table["revenue_growth"] = known["revenue_ttm"] / positive(known["revenue_prior"]) - 1
        prior_income = known["net_income_prior"].where(known["net_income_prior"] != 0)
        table["earnings_growth"] = (known["net_income_ttm"] - prior_income) / prior_income.abs()
        table["profit_margin"] = known["net_income_ttm"] / positive(known["revenue_ttm"])
        real_close = prices["close"] * split_factor(splits, calendar)
        table["pe_ratio"] = real_close / positive(known["eps_diluted_ttm"])
        table["debt_to_equity"] = known["liabilities"] / positive(known["equity"])

    if earnings is not None and not earnings.empty:
        reported = earnings.dropna(subset=["eps_reported"])
        days = reported["announced"].dt.normalize()
        surprise = pd.Series(reported["surprise_percent"].to_numpy(), index=days)
        surprise = surprise[~surprise.index.duplicated(keep="last")]
        table["earnings_surprise"] = _asof(calendar, surprise, exact=False)
        last_day = _asof(calendar, pd.Series(days.to_numpy(), index=days), exact=False)
        # Position of the announcement in the trading calendar (the next trading day if
        # it was announced on a day the market was closed).
        last_position = calendar.searchsorted(pd.DatetimeIndex(last_day.fillna(calendar[0])))
        since = pd.Series(np.arange(len(calendar)) - last_position + 0.0, index=calendar)
        table["days_since_earnings"] = since.where(last_day.notna())

    for column, (low, high) in COMPANY_LIMITS.items():
        table[column] = table[column].astype(float).clip(low, high)
    return table


def fill_company_gaps(table: pd.DataFrame) -> pd.DataFrame:
    """Fill each missing company input with that day's median across all stocks, and
    set financials_missing to 1 where anything was filled in."""
    result = table.copy()
    missing = result[COMPANY_FEATURES].isna()
    result["financials_missing"] = missing.any(axis=1).astype(float)
    medians = result.groupby(level=0)[COMPANY_FEATURES].transform("median")
    result[COMPANY_FEATURES] = result[COMPANY_FEATURES].fillna(medians)
    overall = result[COMPANY_FEATURES].median()
    result[COMPANY_FEATURES] = result[COMPANY_FEATURES].fillna(overall).fillna(0.0)
    return result
