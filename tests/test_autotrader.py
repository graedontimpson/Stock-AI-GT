"""The AI trader: its own account, buying at 60% or more and selling at 40% or less."""

import pytest

from stock_ai import account, autotrader, storage
from stock_ai.shapes import DailyResults, Suggestion


def results(day, chances):
    """Daily results where every suggestion shown to the user is Hold, as when the model
    has not beaten the baseline. The AI trader goes by the chances alone."""
    suggestions = [Suggestion(ticker, ticker, day, "hold", chance, "low", "medium", 0.55, 0.58, False)
                   for ticker, chance in chances.items()]
    return DailyResults(day, suggestions, [], [], None, {})


def test_buys_at_60_percent_or_more_highest_first(quotes):
    report = autotrader.run(results("2026-10-27", {"BBB": 0.62, "AAA": 0.70, "CCC": 0.55, "DDD": 0.40}))

    # About 5% of $100,000 each: 50 shares of AAA at $100, then 100 of BBB at $50.
    assert [(t.ticker, t.shares, t.suggestion_at_time) for t in report.bought] == [
        ("AAA", 50, "buy"), ("BBB", 100, "buy")]
    assert report.sold == []
    cash, positions = account.cash_and_positions("ai")
    assert cash == pytest.approx(90_000)
    assert set(positions) == {"AAA", "BBB"}


def test_never_touches_your_account(quotes):
    autotrader.run(results("2026-10-27", {"AAA": 0.70}))
    assert storage.load_account("you") is None
    assert storage.load_trades("you") == []


def test_sells_the_whole_holding_only_at_sell(quotes):
    autotrader.run(results("2026-10-27", {"AAA": 0.70, "BBB": 0.70}))

    report = autotrader.run(results("2026-10-28", {"AAA": 0.40, "BBB": 0.50}))

    assert [(t.ticker, t.kind, t.shares) for t in report.sold] == [("AAA", "sell", 50)]
    _, positions = account.cash_and_positions("ai")
    assert set(positions) == {"BBB"}  # Hold keeps it


def test_does_not_buy_more_of_a_stock_it_owns(quotes):
    autotrader.run(results("2026-10-27", {"AAA": 0.70}))
    report = autotrader.run(results("2026-10-28", {"AAA": 0.75}))
    assert report.bought == []


def test_trades_at_most_once_a_day(quotes):
    autotrader.run(results("2026-10-27", {"AAA": 0.70}))
    report = autotrader.run(results("2026-10-27", {"AAA": 0.20, "BBB": 0.90}))
    assert report.already_ran
    assert len(storage.load_trades("ai")) == 1


def test_stops_when_less_than_half_a_buy_is_left(quotes, monkeypatch):
    monkeypatch.setattr(autotrader, "AI_BUY_FRACTION", 0.45)
    quotes.prices["CCC"] = 10.0

    report = autotrader.run(results("2026-10-27", {"AAA": 0.80, "BBB": 0.70, "CCC": 0.65}))

    # $45,000 each into AAA and BBB leaves $10,000, under half of $45,000.
    assert [t.ticker for t in report.bought] == ["AAA", "BBB"]


def test_a_stock_without_a_price_is_skipped_and_the_rest_still_trade(quotes):
    quotes.prices.pop("AAA")
    report = autotrader.run(results("2026-10-27", {"AAA": 0.80, "BBB": 0.70}))
    assert "AAA" in report.problems
    assert [t.ticker for t in report.bought] == ["BBB"]


def test_rule_edges():
    def action(chance):
        return autotrader.rule_action(results("d", {"AAA": chance}).suggestions[0])
    assert [action(c) for c in (0.60, 0.59, 0.41, 0.40)] == ["buy", "hold", "hold", "sell"]
