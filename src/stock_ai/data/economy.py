"""Economic indicators from FRED."""

import io

import pandas as pd
import requests

from stock_ai import storage
from stock_ai.errors import DataUnavailableError

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={code}"
SERIES = ["DFF", "CPIAUCSL", "UNRATE", "VIXCLS"]


def _fetch_series(code: str) -> str:
    # FRED refuses custom User-Agent headers, so none is sent.
    for attempt in range(2):
        try:
            response = requests.get(FRED_URL.format(code=code), timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            if attempt == 1:
                raise


def parse_series(text: str, code: str) -> pd.Series:
    """FRED's CSV has a date column and a value column. Missing values (blanks or
    dots) are removed here; the previous value is carried forward when signals
    are built."""
    table = pd.read_csv(io.StringIO(text))
    dates = pd.to_datetime(table.iloc[:, 0])
    values = pd.to_numeric(table.iloc[:, 1], errors="coerce")
    series = pd.Series(values.to_numpy(), index=dates, name=code).dropna()
    series.index.name = "date"
    return series


def get_economy(refresh: bool = False) -> pd.DataFrame:
    saved = storage.load_economy()
    if saved is not None and not refresh and storage.saved_today(storage.economy_path()):
        saved.attrs["out_of_date"] = False
        return saved
    try:
        series = [parse_series(_fetch_series(code), code) for code in SERIES]
    except Exception:
        if saved is None:
            raise DataUnavailableError()
        saved.attrs["out_of_date"] = True
        return saved
    economy = pd.concat(series, axis=1).sort_index()
    storage.save_economy(economy)
    economy.attrs["out_of_date"] = False
    return economy
