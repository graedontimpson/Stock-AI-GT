import numpy as np
import pandas as pd
import pytest

from stock_ai import jev, pipeline, storage
from stock_ai.data import economy, prices, universe
from stock_ai.errors import DataUnavailableError, NotInSP500Error
from stock_ai.shapes import JevExplanation
from tests.conftest import FIXTURES, random_walk_prices, synthetic_economy


@pytest.fixture
def services(monkeypatch, sp500_saved):
    """Seven years of made-up prices for AAA, BBB, CCC and SPY, served as if from Yahoo."""
    rng = np.random.default_rng(5)
    days = pd.bdate_range("2017-01-02", "2023-12-29")
    tables = {t: random_walk_prices(rng, days).drop(columns="filled") for t in ["SPY", "AAA", "BBB", "CCC"]}
    tables["CCC"] = tables["CCC"].iloc[-150:]  # under a year of prices
    universe_table = pd.read_csv(FIXTURES / "sp500.csv")
    monkeypatch.setattr(universe, "get_sp500", lambda refresh=False: universe_table)

    def fake_download(tickers, period):
        return {t: tables[t] for t in tickers if t in tables}
    monkeypatch.setattr(prices, "_download", fake_download)
    monkeypatch.setattr(prices, "_complete_days", lambda table, now=None: table)
    monkeypatch.setattr(economy, "get_economy", lambda refresh=False: synthetic_economy(days))
    return tables


def test_daily_run(services):
    messages = []
    results = pipeline.run_daily(progress=messages.append)
    assert {s.ticker for s in results.suggestions} == {"AAA", "BBB"}
    assert results.skipped["CCC"] == "under 1 year of prices"
    assert "DDD" in results.skipped  # Yahoo returned nothing for it
    assert results.backtest is not None
    for s in results.suggestions:
        assert 0 < s.probability_up < 1
        assert s.action in {"buy", "hold", "sell"}
        assert s.as_of == "2023-12-29"
    assert any("backtest" in m for m in messages)
    assert storage.load_results(results.date) is not None


def test_second_run_same_day_reuses_results(services, monkeypatch):
    first = pipeline.run_daily()

    def should_not_run(*args, **kwargs):
        raise AssertionError("recalculated")
    monkeypatch.setattr(prices, "update_history", should_not_run)
    assert pipeline.run_daily() == first


def test_missing_spy_raises(services):
    del services["SPY"]
    with pytest.raises(DataUnavailableError):
        pipeline.run_daily()


def test_get_suggestion(services):
    pipeline.run_daily()
    assert pipeline.get_suggestion("aaa").ticker == "AAA"
    assert pipeline.get_suggestion("CCC") is None
    with pytest.raises(NotInSP500Error):
        pipeline.get_suggestion("ZZZ")


def test_explanation_requested_once_per_day(services, monkeypatch):
    from datetime import date
    pipeline.run_daily()
    calls = []

    def fake_explain(suggestion, shares_owned):
        calls.append(suggestion.ticker)
        return JevExplanation(suggestion.ticker, str(date.today()), "ok", why="w")
    monkeypatch.setattr(jev, "explain", fake_explain)
    assert pipeline.get_explanation("AAA").why == "w"
    assert pipeline.get_explanation("AAA").why == "w"
    assert calls == ["AAA"]  # the second request was served from storage


def test_failed_explanation_is_not_saved(services, monkeypatch):
    pipeline.run_daily()
    calls = []

    def failing_explain(suggestion, shares_owned):
        calls.append(1)
        return JevExplanation(suggestion.ticker, "today", "unavailable", reason="x")
    monkeypatch.setattr(jev, "explain", failing_explain)
    pipeline.get_explanation("AAA")
    pipeline.get_explanation("AAA")
    assert len(calls) == 2  # tried again, since nothing useful was saved
