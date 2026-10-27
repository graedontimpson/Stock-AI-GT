"""Earnings announcements and surprises from Yahoo Finance."""

import time
from dataclasses import dataclass, field

import pandas as pd
import yfinance as yf

from stock_ai import storage

REQUEST_PAUSE_SECONDS = 0.5
COLUMNS = ["announced", "eps_expected", "eps_reported", "surprise_percent"]


@dataclass
class UpdateReport:
    updated: list = field(default_factory=list)
    failed: dict = field(default_factory=dict)


def _fetch(ticker: str) -> pd.DataFrame:
    return yf.Ticker(ticker).get_earnings_dates(limit=60)


def _fetch_splits(ticker: str) -> pd.Series:
    return yf.Ticker(ticker).splits


def clean_splits(raw: pd.Series) -> pd.DataFrame:
    """Split history: one row per split with its date and ratio (new shares per old)."""
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=["date", "ratio"])
    index = pd.DatetimeIndex(raw.index)
    if index.tz is not None:
        index = index.tz_convert("America/New_York").tz_localize(None)
    table = pd.DataFrame({"date": index.normalize(), "ratio": raw.to_numpy(dtype=float)})
    return table[table["ratio"] > 0].sort_values("date").reset_index(drop=True)


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per announcement, oldest first. Upcoming announcements have no
    reported figures yet and are kept so the next date can be shown."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=COLUMNS)
    index = pd.DatetimeIndex(raw.index)
    if index.tz is not None:
        index = index.tz_convert("America/New_York").tz_localize(None)
    table = pd.DataFrame({
        "announced": index,
        "eps_expected": pd.to_numeric(raw["EPS Estimate"], errors="coerce").to_numpy(),
        "eps_reported": pd.to_numeric(raw["Reported EPS"], errors="coerce").to_numpy(),
        "surprise_percent": pd.to_numeric(raw["Surprise(%)"], errors="coerce").to_numpy(),
    })
    return table.drop_duplicates("announced").sort_values("announced").reset_index(drop=True)


def update(tickers: list[str], refresh: bool = False, progress=None) -> UpdateReport:
    """Weekly. A ticker saved in the last 7 days is skipped unless refresh=True."""
    report = UpdateReport()
    for number, ticker in enumerate(tickers, start=1):
        if progress and number % 50 == 1:
            progress(f"Downloading earnings history: {number} of {len(tickers)}")
        if not refresh and storage.saved_within_days(storage.earnings_path(ticker), 7):
            continue
        try:
            table = clean(_fetch(ticker))
            splits = clean_splits(_fetch_splits(ticker))
        except Exception as error:
            report.failed[ticker] = f"download failed: {error}"
            continue
        finally:
            time.sleep(REQUEST_PAUSE_SECONDS)
        storage.save_earnings(ticker, table)
        storage.save_splits(ticker, splits)
        report.updated.append(ticker)
    return report


def next_announcement(ticker: str, today: pd.Timestamp | None = None) -> pd.Timestamp | None:
    table = storage.load_earnings(ticker)
    if table is None:
        return None
    today = today or pd.Timestamp.today().normalize()
    upcoming = table[table["announced"] >= today]
    return upcoming["announced"].min() if not upcoming.empty else None
