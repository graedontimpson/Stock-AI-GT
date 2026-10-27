"""universe.py, prices.py, and economy.py, with every download replaced by fixture data."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from stock_ai import storage
from stock_ai.data import economy, prices, universe
from stock_ai.errors import DataUnavailableError, PriceUnavailableError
from tests.conftest import FIXTURES, fred_text, raw_prices


def wikipedia_table(rows=503):
    return pd.DataFrame({
        "Symbol": ["BRK.B", "BF.B", "BRK.B"] + [f"T{i:03d}" for i in range(rows - 3)],
        "Security": ["Berkshire", "Brown-Forman", "Berkshire again"] + ["Co"] * (rows - 3),
        "GICS Sector": ["Financials"] * rows,
        "CIK": [0] * rows,
    })


# universe.py

def test_universe_converts_dots_and_removes_duplicates(monkeypatch):
    monkeypatch.setattr(universe, "_fetch_table", lambda: wikipedia_table(504))
    table = universe.get_sp500()
    assert "BRK-B" in set(table["ticker"]) and "BF-B" in set(table["ticker"])
    assert not table["ticker"].duplicated().any()
    assert list(table.columns) == ["ticker", "company_name", "sector", "downloaded"]
    assert table.attrs["out_of_date"] is False


@pytest.mark.parametrize("rows", [480, 520])
def test_universe_rejects_wrong_size_and_uses_saved(monkeypatch, sp500_saved, rows):
    monkeypatch.setattr(universe, "_fetch_table", lambda: wikipedia_table(rows))
    table = universe.get_sp500(refresh=True)
    assert table.attrs["out_of_date"] is True
    assert list(table["ticker"]) == ["AAA", "BBB", "CCC", "DDD"]


def test_universe_with_nothing_saved_raises(monkeypatch):
    def broken():
        raise ConnectionError
    monkeypatch.setattr(universe, "_fetch_table", broken)
    with pytest.raises(DataUnavailableError):
        universe.get_sp500()


def test_is_in_sp500(sp500_saved):
    assert universe.is_in_sp500("AAA")
    assert universe.is_in_sp500("aaa")
    assert not universe.is_in_sp500("ZZZ")


# prices.py: cleaning

def test_clean_removes_days_without_close_and_duplicates():
    raw = raw_prices("AAA").iloc[:10].copy()
    raw.iloc[3, raw.columns.get_loc("close")] = float("nan")
    raw = pd.concat([raw, raw.iloc[[5]].assign(close=999.0)])
    cleaned = prices.clean(raw, None)
    assert len(cleaned) == 9
    assert cleaned.loc[raw.index[5], "close"] == 999.0  # the last copy is kept


def test_clean_fills_short_gap():
    market = prices.clean(raw_prices("SPY"), None)
    cleaned = prices.clean(raw_prices("BBB"), market.index)
    missing_day = market.index[300]
    assert cleaned.loc[missing_day, "filled"]
    assert cleaned.loc[missing_day, "volume"] == 0
    assert cleaned.loc[missing_day, "close"] == cleaned.loc[market.index[299], "close"]
    assert cleaned["filled"].sum() == 1


def test_clean_skips_long_gap_and_zero_price():
    market = prices.clean(raw_prices("SPY"), None)
    with pytest.raises(prices.SkipTicker, match="gap of 8"):
        prices.clean(raw_prices("CCC"), market.index)
    with pytest.raises(prices.SkipTicker, match="zero"):
        prices.clean(raw_prices("DDD"), market.index)


# prices.py: updating saved history

class FakeYahoo:
    def __init__(self, tables):
        self.tables = tables
        self.calls = []

    def __call__(self, tickers, period):
        self.calls.append((tuple(tickers), period))
        full = period.endswith("y")
        result = {}
        for ticker in tickers:
            if ticker in self.tables:
                table = self.tables[ticker]
                result[ticker] = table if full else table.iloc[-21:]
        return result


@pytest.fixture
def frozen_today(monkeypatch):
    """Make 'today' just after the fixture data ends, after the market has settled."""
    moment = datetime(2025, 1, 2, 18, 0, tzinfo=prices.NEW_YORK)
    real_complete_days = prices._complete_days
    monkeypatch.setattr(prices, "_complete_days", lambda table, now=None: real_complete_days(table, moment))
    monkeypatch.setattr(pd.Timestamp, "today", classmethod(lambda cls: pd.Timestamp("2025-01-02")))


def test_update_history_first_run_and_skips(monkeypatch, frozen_today):
    fake = FakeYahoo({t: raw_prices(t) for t in ["SPY", "AAA", "BBB", "CCC", "DDD"]})
    monkeypatch.setattr(prices, "_download", fake)
    report = prices.update_history(["AAA", "BBB", "CCC", "DDD", "EEE"])
    assert set(report.updated) == {"SPY", "AAA", "BBB"}
    assert "gap" in report.failed["CCC"]
    assert "zero" in report.failed["DDD"]
    assert report.failed["EEE"] == "no data returned"
    assert storage.load_prices("AAA") is not None


def test_update_history_appends_when_unchanged(monkeypatch, frozen_today):
    full = {t: raw_prices(t) for t in ["SPY", "AAA"]}
    for ticker, table in full.items():
        storage.save_prices(ticker, prices.clean(table.iloc[:-5], None))
    fake = FakeYahoo(full)
    monkeypatch.setattr(prices, "_download", fake)
    report = prices.update_history(["AAA"])
    assert report.redownloaded == []
    assert all(period == "1mo" for _, period in fake.calls)
    assert len(storage.load_prices("AAA")) == len(full["AAA"])


def test_update_history_redownloads_when_yahoo_changed_the_past(monkeypatch, frozen_today):
    full = {t: raw_prices(t) for t in ["SPY", "AAA"]}
    for ticker, table in full.items():
        storage.save_prices(ticker, prices.clean(table.iloc[:-5], None))
    changed = full["AAA"].copy()
    changed["adj_close"] *= 0.99  # as if a dividend changed every earlier adjusted price
    monkeypatch.setattr(prices, "_download", FakeYahoo({"SPY": full["SPY"], "AAA": changed}))
    report = prices.update_history(["AAA"])
    assert report.redownloaded == ["AAA"]
    assert storage.load_prices("AAA")["adj_close"].iloc[0] == pytest.approx(changed["adj_close"].iloc[0])


def test_failed_batch_is_retried_once(monkeypatch, frozen_today):
    attempts = []

    def flaky(tickers, period):
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("refused")
        return {t: raw_prices(t) for t in tickers}
    monkeypatch.setattr(prices, "_download", flaky)
    report = prices.update_history(["AAA"])
    assert len(attempts) == 2
    assert "AAA" in report.updated


# prices.py: latest prices and splits

def test_latest_price_refuses_bad_answers(monkeypatch):
    now = datetime(2024, 6, 5, 11, 0, tzinfo=prices.NEW_YORK)
    for answer in [None, (0.0, now), (-1.0, now), (100.0, now - timedelta(days=5))]:
        monkeypatch.setattr(prices, "_fetch_quote", lambda ticker, a=answer: a)
        with pytest.raises(PriceUnavailableError):
            prices.get_latest_price("AAA", now=now)

    def broken(ticker):
        raise ConnectionError
    monkeypatch.setattr(prices, "_fetch_quote", broken)
    with pytest.raises(PriceUnavailableError):
        prices.get_latest_price("AAA", now=now)


def test_latest_price_ok_and_over_a_weekend(monkeypatch):
    friday_close = datetime(2024, 6, 7, 15, 59, tzinfo=prices.NEW_YORK)
    monkeypatch.setattr(prices, "_fetch_quote", lambda ticker: (123.45, friday_close))
    quote = prices.get_latest_price("AAA", now=datetime(2024, 6, 10, 9, 0, tzinfo=prices.NEW_YORK))
    assert quote.price == 123.45
    assert quote.market_open is False
    open_now = prices.get_latest_price("AAA", now=datetime(2024, 6, 7, 15, 59, 30, tzinfo=prices.NEW_YORK))
    assert open_now.market_open is True


def test_latest_price_never_uses_saved_prices(monkeypatch, prices_saved):
    monkeypatch.setattr(prices, "_fetch_quote", lambda ticker: None)
    with pytest.raises(PriceUnavailableError):
        prices.get_latest_price("AAA")


def test_get_splits_filters_by_date(monkeypatch):
    splits = pd.Series([4.0, 2.0], index=pd.DatetimeIndex(
        ["2020-08-31 09:30", "2024-06-10 09:30"]).tz_localize(prices.NEW_YORK))
    monkeypatch.setattr(prices, "_fetch_splits", lambda ticker: splits)
    found = prices.get_splits("AAA", since=datetime(2021, 1, 1, tzinfo=prices.NEW_YORK))
    assert [(s.ratio, s.date.year) for s in found] == [(2.0, 2024)]


def test_get_splits_unreachable_returns_empty(monkeypatch):
    def broken(ticker):
        raise ConnectionError
    monkeypatch.setattr(prices, "_fetch_splits", broken)
    assert prices.get_splits("AAA", since=datetime(2021, 1, 1, tzinfo=prices.NEW_YORK)) == []


# economy.py

def test_parse_series_drops_blanks_and_dots():
    text = "observation_date,UNRATE\n2023-09-01,3.8\n2023-10-01,\n2023-11-01,.\n2023-12-01,3.7\n"
    series = economy.parse_series(text, "UNRATE")
    assert list(series.index.strftime("%Y-%m")) == ["2023-09", "2023-12"]


def test_get_economy_downloads_and_saves(monkeypatch):
    monkeypatch.setattr(economy, "_fetch_series", fred_text)
    table = economy.get_economy()
    assert list(table.columns) == economy.SERIES
    assert table.attrs["out_of_date"] is False
    assert storage.load_economy() is not None


def test_get_economy_failure_uses_saved(monkeypatch):
    monkeypatch.setattr(economy, "_fetch_series", fred_text)
    economy.get_economy()

    def broken(code):
        raise ConnectionError
    monkeypatch.setattr(economy, "_fetch_series", broken)
    assert economy.get_economy(refresh=True).attrs["out_of_date"] is True


def test_get_economy_failure_with_nothing_saved(monkeypatch):
    def broken(code):
        raise ConnectionError
    monkeypatch.setattr(economy, "_fetch_series", broken)
    with pytest.raises(DataUnavailableError):
        economy.get_economy()
