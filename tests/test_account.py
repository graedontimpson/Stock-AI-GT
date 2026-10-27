"""The paper trading account: QA section 4."""

from datetime import datetime, timedelta

import pytest

from stock_ai import account, storage
from stock_ai.data import prices
from stock_ai.errors import (
    InvalidSharesError,
    NotEnoughCashError,
    NotEnoughSharesError,
    NotInSP500Error,
    PriceUnavailableError,
)
from stock_ai.shapes import DailyResults, Split, Suggestion


def check_rules():
    """The rules that must always hold, checked after every step."""
    acct = storage.load_account()
    trades = storage.load_trades()
    cash, positions = account.cash_and_positions()
    expected_cash = acct.starting_cash
    shares = {}
    for t in trades:
        if t.kind == "buy":
            expected_cash -= t.shares * t.price
            shares[t.ticker] = shares.get(t.ticker, 0) + t.shares
        elif t.kind == "sell":
            expected_cash += t.shares * t.price
            shares[t.ticker] = shares.get(t.ticker, 0) - t.shares
        else:
            shares[t.ticker] = shares.get(t.ticker, 0) + t.shares
    assert cash >= 0
    assert cash == pytest.approx(expected_cash, abs=0.01)
    for ticker, count in shares.items():
        assert count >= 0
        assert (positions[ticker].shares if ticker in positions else 0) == count
    portfolio = account.get_portfolio()
    assert portfolio.total_value == pytest.approx(portfolio.cash + sum(h.value for h in portfolio.holdings), abs=0.01)
    assert [t.id for t in trades] == list(range(1, len(trades) + 1))


@pytest.fixture
def opened(quotes):
    account.open_account()
    return quotes


def test_new_account(opened):
    acct = storage.load_account()
    assert acct.starting_cash == 100_000
    assert acct.benchmark_shares == pytest.approx(250.0)
    performance = account.get_performance()
    assert performance.account_gain_percent == pytest.approx(0)
    assert performance.benchmark_gain_percent == pytest.approx(0)


def test_open_account_needs_a_spy_price(quotes):
    del quotes.prices["SPY"]
    with pytest.raises(PriceUnavailableError):
        account.open_account()


def test_buy_with_enough_cash(opened):
    trade = account.buy("AAA", 10)
    assert (trade.kind, trade.shares, trade.price) == ("buy", 10, 100.0)
    cash, _ = account.cash_and_positions()
    assert cash == 99_000
    check_rules()


def test_buy_exactly_all_the_cash(opened):
    opened.prices["AAA"] = 1000.0
    account.buy("AAA", 100)
    assert account.cash_and_positions()[0] == 0
    check_rules()


def test_buy_one_cent_too_much(opened):
    opened.prices["AAA"] = 1000.0001
    with pytest.raises(NotEnoughCashError) as error:
        account.buy("AAA", 100)
    assert "$100,000.01" in error.value.message
    assert storage.load_trades() == []


@pytest.mark.parametrize("shares", [0, -1, 1.5, True, "3"])
def test_invalid_share_counts(opened, shares):
    with pytest.raises(InvalidSharesError):
        account.buy("AAA", shares)
    assert storage.load_trades() == []


def test_buy_outside_sp500(opened):
    with pytest.raises(NotInSP500Error):
        account.buy("ZZZ", 1)
    assert storage.load_trades() == []


def test_buy_without_a_price(opened):
    del opened.prices["AAA"]
    with pytest.raises(PriceUnavailableError):
        account.buy("AAA", 1)
    assert storage.load_trades() == []


def test_sell_part_then_all(opened):
    account.buy("AAA", 10)
    opened.prices["AAA"] = 120.0
    account.sell("AAA", 4)
    _, positions = account.cash_and_positions()
    assert positions["AAA"].shares == 6
    assert positions["AAA"].average_cost == pytest.approx(100.0)
    check_rules()
    account.sell("AAA", 6)
    assert "AAA" not in account.cash_and_positions()[1]
    assert account.get_portfolio().holdings == []
    assert account.cash_and_positions()[0] == pytest.approx(100_000 + 10 * 20)
    check_rules()


@pytest.mark.parametrize("owned, selling", [(5, 6), (0, 1)])
def test_sell_more_than_owned(opened, owned, selling):
    if owned:
        account.buy("AAA", owned)
    with pytest.raises(NotEnoughSharesError) as error:
        account.sell("AAA", selling)
    assert f"You own {owned} shares of AAA" in error.value.message
    assert len(storage.load_trades()) == (1 if owned else 0)


def test_sell_stock_that_left_the_sp500(opened, sp500_saved):
    account.buy("AAA", 3)
    table = storage.load_sp500()
    storage.save_sp500(table[table["ticker"] != "AAA"])
    account.sell("AAA", 3)
    check_rules()


def test_average_cost_is_weighted(opened):
    account.buy("AAA", 10)
    opened.prices["AAA"] = 130.0
    account.buy("AAA", 20)
    assert account.cash_and_positions()[1]["AAA"].average_cost == pytest.approx(120.0)
    check_rules()


def test_two_for_one_split(opened):
    account.buy("AAA", 10)
    before = account.get_portfolio().holdings[0]
    split_day = datetime.now(prices.NEW_YORK) + timedelta(seconds=1)
    opened.splits["AAA"] = [Split("AAA", split_day, 2.0)]
    opened.prices["AAA"] = 50.0  # the price halves with the split
    added = account.apply_splits()
    assert [(t.kind, t.shares) for t in added] == [("split", 10)]
    after = account.get_portfolio().holdings[0]
    assert after.shares == 20
    assert after.average_cost == pytest.approx(before.average_cost / 2)
    assert after.value == pytest.approx(before.value)
    assert after.gain == pytest.approx(before.gain)
    check_rules()
    assert account.apply_splits() == []  # the same split is only applied once
    check_rules()


def test_split_before_buying_is_ignored(opened):
    opened.splits["AAA"] = [Split("AAA", datetime.now(prices.NEW_YORK) - timedelta(days=30), 4.0)]
    account.buy("AAA", 10)
    assert account.apply_splits() == []


def test_reset_archives_and_starts_fresh(opened, isolated):
    account.buy("AAA", 10)
    account.reset()
    assert storage.load_trades() == []
    assert account.cash_and_positions()[0] == 100_000
    assert len(list((isolated / "account" / "archive").iterdir())) == 1


def test_trade_records_the_suggestion(opened):
    suggestion = Suggestion("AAA", "Alpha", "2024-01-02", "buy", 0.7, "high", "low", 0.6, 0.5, True, [])
    storage.save_results(DailyResults("2024-01-02", [suggestion], [suggestion], [], None, {}))
    assert account.buy("AAA", 1).suggestion_at_time == "buy"
    assert account.buy("BBB", 1).suggestion_at_time == ""


def test_performance_against_spy(opened):
    account.buy("AAA", 100)  # $10,000
    opened.prices["AAA"] = 110.0  # account gains $1,000 = 1%
    opened.prices["SPY"] = 404.0  # SPY gains 1% too
    performance = account.get_performance()
    assert performance.account_gain_percent == pytest.approx(1.0)
    assert performance.benchmark_gain_percent == pytest.approx(1.0)
    assert performance.ahead_by == pytest.approx(0.0)


def test_portfolio_falls_back_to_saved_close(opened, prices_saved):
    account.buy("AAA", 2)
    del opened.prices["AAA"]
    holding = account.get_portfolio().holdings[0]
    assert holding.price_is_fallback
    assert holding.current_price == pytest.approx(storage.load_prices("AAA")["close"].iloc[-1])
