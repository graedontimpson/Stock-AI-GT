"""The S&P 500 list, read from Wikipedia."""

import io
from datetime import datetime

import pandas as pd
import requests

from stock_ai import storage
from stock_ai.config import load_settings
from stock_ai.errors import DataUnavailableError

# Wikipedia asks for a descriptive User-Agent.
HEADERS = {"User-Agent": "stock-ai/0.1 (personal paper trading project)"}
MIN_ROWS, MAX_ROWS = 490, 510


def _fetch_table() -> pd.DataFrame:
    response = requests.get(load_settings().sp500_source, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return pd.read_html(io.StringIO(response.text))[0]


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Keep ticker, name, and sector; use Yahoo's ticker form; reject a broken table."""
    table = raw.rename(columns={"Symbol": "ticker", "Security": "company_name", "GICS Sector": "sector"})
    table = table[["ticker", "company_name", "sector"]].copy()
    table["ticker"] = table["ticker"].astype(str).str.strip().str.replace(".", "-", regex=False)
    table = table.drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)
    if not MIN_ROWS <= len(table) <= MAX_ROWS:
        raise ValueError(f"S&P 500 table has {len(table)} rows")
    table["downloaded"] = datetime.now().isoformat(timespec="seconds")
    return table


def get_sp500(refresh: bool = False) -> pd.DataFrame:
    saved = storage.load_sp500()
    if saved is not None and not refresh and storage.saved_today(storage.sp500_path()):
        saved.attrs["out_of_date"] = False
        return saved
    try:
        table = clean(_fetch_table())
    except Exception:
        if saved is None:
            raise DataUnavailableError()
        saved.attrs["out_of_date"] = True
        return saved
    storage.save_sp500(table)
    table.attrs["out_of_date"] = False
    return table


def is_in_sp500(ticker: str) -> bool:
    table = storage.load_sp500()
    if table is None:
        table = get_sp500()
    return ticker.upper() in set(table["ticker"])


def company_name(ticker: str) -> str:
    table = storage.load_sp500()
    if table is not None:
        match = table.loc[table["ticker"] == ticker, "company_name"]
        if len(match):
            return str(match.iloc[0])
    return ticker
