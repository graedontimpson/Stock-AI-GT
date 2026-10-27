from datetime import datetime

import pandas as pd

from stock_ai import config, storage
from stock_ai.shapes import Account, BacktestResult, DailyResults, JevExplanation, Suggestion, Trade


def test_defaults_with_empty_env(isolated):
    settings = config.load_settings()
    assert settings.data_dir == isolated
    assert settings.anthropic_api_key is None
    assert not settings.has_api_key
    assert settings.jev_model == "claude-opus-5-5"
    assert settings.starting_cash == 100_000
    assert (settings.buy_threshold, settings.sell_threshold) == (0.60, 0.40)


def test_reads_key_and_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("JEV_MODEL", "claude-sonnet-5-5")
    settings = config.load_settings()
    assert settings.has_api_key
    assert settings.jev_model == "claude-sonnet-5-5"


def test_key_never_shown_when_printed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-secret-value")
    assert "sk-test-secret-value" not in repr(config.load_settings())


def test_load_missing_files_returns_nothing():
    assert storage.load_prices("AAA") is None
    assert storage.load_economy() is None
    assert storage.load_account() is None
    assert storage.load_trades() == []
    assert storage.load_results("2024-01-01") is None
    assert storage.latest_backtest() is None
    assert storage.load_explanations("2024-01-01") == {}
    assert storage.load_scorecard().empty


def test_prices_round_trip():
    table = pd.DataFrame({"close": [1.5, 2.5], "adj_close": [1.4, 2.4]},
                         index=pd.DatetimeIndex(["2024-01-02", "2024-01-03"], name="date"))
    storage.save_prices("AAA", table)
    loaded = storage.load_prices("AAA")
    pd.testing.assert_frame_equal(loaded, table, check_freq=False)


def test_records_round_trip():
    storage.save_account(Account(opened="2024-01-02T10:00:00-05:00", starting_cash=100_000,
                                 benchmark_shares=250.0, benchmark_price=400.0))
    assert storage.load_account().benchmark_shares == 250.0

    suggestion = Suggestion("AAA", "Alpha", "2024-01-02", "buy", 0.66, "medium", "low",
                            0.6, 0.55, True, [])
    backtest = BacktestResult(0.6, 0.55, 100, {"AAA": {"track_record": 0.6}}, "2020-01-01",
                              "2024-01-01", "2024-01-02")
    results = DailyResults("2024-01-02", [suggestion], [suggestion], [], backtest, {"CCC": "gap"})
    storage.save_results(results)
    loaded = storage.load_results("2024-01-02")
    assert loaded.suggestions[0] == suggestion
    assert loaded.backtest == backtest
    assert loaded.find("AAA") == suggestion

    storage.save_explanation(JevExplanation("AAA", "2024-01-02", "ok", why="w"))
    assert storage.load_explanations("2024-01-02")["AAA"].why == "w"


def test_append_trade_never_changes_earlier_rows(isolated):
    first = Trade(1, "2024-01-02T10:00:00-05:00", "AAA", "buy", 10, 100.0, "t", "buy")
    storage.append_trade(first)
    before = (isolated / "account" / "trades.csv").read_text()
    storage.append_trade(Trade(2, "2024-01-03T10:00:00-05:00", "AAA", "sell", 5, 110.0, "t", ""))
    after = (isolated / "account" / "trades.csv").read_text()
    assert after.startswith(before)
    trades = storage.load_trades()
    assert [t.id for t in trades] == [1, 2]
    assert trades[0] == first


def test_archive_account_copies_then_clears(isolated):
    storage.save_account(Account("2024-01-02T10:00:00", 100_000, 250.0, 400.0))
    storage.append_trade(Trade(1, "2024-01-02T10:00:00", "AAA", "buy", 1, 1.0, "t", ""))
    storage.archive_account()
    archived = list((isolated / "account" / "archive").iterdir())
    assert len(archived) == 1
    assert {p.name for p in archived[0].iterdir()} == {"account.json", "trades.csv"}
    assert storage.load_account() is None
    assert storage.load_trades() == []
