"""Shared test setup. Tests never touch the real data/ folder, the real .env, or the internet."""

import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stock_ai import config
from stock_ai.data import prices
from stock_ai.data.economy import parse_series
from stock_ai.shapes import Quote
from stock_ai.signals import FEATURES

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets an empty data folder and no API key."""
    monkeypatch.setenv("STOCK_AI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("JEV_MODEL", raising=False)
    monkeypatch.setattr(config, "dotenv_values", lambda *args, **kwargs: {})
    monkeypatch.setattr(prices, "BATCH_PAUSE_SECONDS", 0)
    monkeypatch.setattr(prices, "RETRY_PAUSE_SECONDS", 0)
    yield tmp_path / "data"


def raw_prices(ticker: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURES / "prices" / f"{ticker}.csv", parse_dates=["date"]).set_index("date")


def fred_text(code: str) -> str:
    return (FIXTURES / "fred" / f"{code}.csv").read_text()


def fixture_economy() -> pd.DataFrame:
    codes = ["DFF", "CPIAUCSL", "UNRATE", "VIXCLS"]
    return pd.concat([parse_series(fred_text(code), code) for code in codes], axis=1).sort_index()


@pytest.fixture
def sp500_saved(isolated):
    isolated.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / "sp500.csv", isolated / "sp500.csv")
    return isolated


@pytest.fixture
def prices_saved(sp500_saved):
    """Clean fixture prices saved as if the daily update had run."""
    from stock_ai import storage
    market = prices.clean(raw_prices("SPY"), None)
    storage.save_prices("SPY", market)
    for ticker in ["AAA", "BBB"]:
        storage.save_prices(ticker, prices.clean(raw_prices(ticker), market.index))
    return sp500_saved


class FakeQuotes:
    """Stands in for Yahoo's latest price. Set `prices[ticker]`; a missing ticker has no price."""

    def __init__(self, monkeypatch):
        self.prices = {"SPY": 400.0, "AAA": 100.0, "BBB": 50.0}
        self.splits = {}
        monkeypatch.setattr(prices, "get_latest_price", self.quote)
        monkeypatch.setattr(prices, "get_splits", self.get_splits)

    def quote(self, ticker, now=None):
        from stock_ai.errors import PriceUnavailableError
        if ticker not in self.prices:
            raise PriceUnavailableError(ticker)
        return Quote(ticker=ticker, price=self.prices[ticker],
                     as_of=datetime.now(prices.NEW_YORK), market_open=True)

    def get_splits(self, ticker, since):
        return [s for s in self.splits.get(ticker, []) if s.date > since]


@pytest.fixture
def quotes(monkeypatch, sp500_saved):
    return FakeQuotes(monkeypatch)


def random_walk_prices(rng, days, drift=0.0, volatility=0.015, start=100.0) -> pd.DataFrame:
    adj = start * np.exp(np.cumsum(rng.normal(drift, volatility, len(days))))
    return pd.DataFrame({
        "open": adj, "high": adj, "low": adj, "close": adj, "adj_close": adj,
        "volume": rng.integers(1_000_000, 2_000_000, len(days)).astype(float),
        "filled": False,
    }, index=pd.DatetimeIndex(days, name="date"))


def synthetic_economy(days) -> pd.DataFrame:
    """Smooth made-up economic data covering `days`, with monthly figures from a year earlier."""
    daily = pd.date_range(days[0] - pd.DateOffset(years=2), days[-1], freq="D")
    months = pd.date_range(daily[0], daily[-1], freq="MS")
    table = pd.DataFrame(index=daily.union(months))
    table["DFF"] = pd.Series(np.linspace(1, 5, len(daily)), index=daily)
    table["VIXCLS"] = pd.Series(18 + 4 * np.sin(np.arange(len(daily)) / 50), index=daily)
    table["CPIAUCSL"] = pd.Series(250 * 1.002 ** np.arange(len(months)), index=months)
    table["UNRATE"] = pd.Series(4 + np.cos(np.arange(len(months)) / 5), index=months)
    return table


def planted_table(rng, rows=40_000, tickers=20) -> pd.DataFrame:
    """Signals where vs_avg_200 really predicts the outcome: rises 70% of the time when
    positive, 40% when negative. Every other signal is noise."""
    days = pd.bdate_range("2014-01-01", periods=rows // tickers)
    frames = []
    for number in range(tickers):
        table = pd.DataFrame(rng.normal(0, 1, (len(days), len(FEATURES))), columns=FEATURES, index=days)
        chance = np.where(table["vs_avg_200"] > 0, 0.7, 0.4)
        table["rose"] = (rng.random(len(days)) < chance).astype(float)
        table.insert(0, "ticker", f"T{number:02d}")
        frames.append(table)
    result = pd.concat(frames)
    result.index.name = "date"
    return result
