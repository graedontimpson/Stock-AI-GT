"""The paper trading account.

The trade list is the single source of truth: cash, holdings, and gains are
always worked out from the starting cash plus the trades, never stored.
"""

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from stock_ai import storage
from stock_ai.config import load_settings
from stock_ai.data import prices, universe
from stock_ai.errors import (
    InvalidSharesError,
    NotEnoughCashError,
    NotEnoughSharesError,
    NotInSP500Error,
    PriceUnavailableError,
)
from stock_ai.shapes import Account, Holding, Performance, Portfolio, Trade

CENT = 0.01


@dataclass
class _Position:
    shares: int = 0
    cost: float = 0.0  # total paid for the shares still held

    @property
    def average_cost(self) -> float:
        return self.cost / self.shares if self.shares else 0.0


def _now() -> str:
    return datetime.now(prices.NEW_YORK).isoformat(timespec="seconds")


def _money(amount: float) -> float:
    return round(amount + 0.0, 2)


def _replay(trades: list[Trade], starting_cash: float, until: datetime | None = None):
    """Cash and positions after the trades (only those before `until`, if given)."""
    cash = starting_cash
    positions: dict[str, _Position] = {}
    for trade in trades:
        if until is not None and datetime.fromisoformat(trade.time) >= until:
            break
        position = positions.setdefault(trade.ticker, _Position())
        if trade.kind == "buy":
            cash -= trade.shares * trade.price
            position.shares += trade.shares
            position.cost += trade.shares * trade.price
        elif trade.kind == "sell":
            cash += trade.shares * trade.price
            position.cost -= trade.shares * position.average_cost
            position.shares -= trade.shares
        elif trade.kind == "split":
            position.shares += trade.shares  # cost is unchanged, so average cost falls
        if position.shares == 0:
            position.cost = 0.0
    return _money(cash), {t: p for t, p in positions.items() if p.shares > 0}


def open_account(owner: str = "you") -> Account:
    """The existing account, or a new one with the starting cash.

    `owner` is "you" for the user's account or "ai" for the AI trader's; every
    function below takes it, and the two accounts never touch each other.
    """
    account = storage.load_account(owner)
    if account is not None:
        return account
    settings = load_settings()
    quote = prices.get_latest_price(settings.market_ticker)
    account = Account(
        opened=_now(),
        starting_cash=settings.starting_cash,
        benchmark_shares=settings.starting_cash / quote.price,
        benchmark_price=quote.price,
    )
    storage.save_account(account, owner)
    return account


def cash_and_positions(owner: str = "you") -> tuple[float, dict]:
    account = open_account(owner)
    return _replay(storage.load_trades(owner), account.starting_cash)


def _check_shares(shares) -> int:
    if isinstance(shares, bool) or not isinstance(shares, (int, float)):
        raise InvalidSharesError()
    if shares != int(shares) or shares < 1:
        raise InvalidSharesError()
    return int(shares)


def _suggestion_now(ticker: str) -> str:
    results = storage.latest_results()
    suggestion = results.find(ticker) if results else None
    return suggestion.action if suggestion else ""


def _record(ticker: str, kind: str, shares: int, price: float | None, price_as_of: str,
            suggestion: str, owner: str = "you") -> Trade:
    trades = storage.load_trades(owner)
    trade = Trade(
        id=(trades[-1].id + 1) if trades else 1,
        time=_now(),
        ticker=ticker,
        kind=kind,
        shares=shares,
        price=price,
        price_as_of=price_as_of,
        suggestion_at_time=suggestion,
    )
    storage.append_trade(trade, owner)
    return trade


def buy(ticker: str, shares, owner: str = "you", suggestion: str | None = None) -> Trade:
    """Buy at the latest price. `suggestion` overrides what is recorded as the AI's view."""
    ticker = ticker.strip().upper()
    shares = _check_shares(shares)
    if not universe.is_in_sp500(ticker):
        raise NotInSP500Error(ticker)
    quote = prices.get_latest_price(ticker)
    cash, _ = cash_and_positions(owner)
    cost = _money(shares * quote.price)
    if cost > cash + 1e-9:
        raise NotEnoughCashError(cost, cash)
    return _record(ticker, "buy", shares, quote.price, quote.as_of.isoformat(),
                   _suggestion_now(ticker) if suggestion is None else suggestion, owner)


def sell(ticker: str, shares, owner: str = "you", suggestion: str | None = None) -> Trade:
    ticker = ticker.strip().upper()
    shares = _check_shares(shares)
    _, positions = cash_and_positions(owner)
    owned = positions[ticker].shares if ticker in positions else 0
    if shares > owned:
        raise NotEnoughSharesError(ticker, owned)
    quote = prices.get_latest_price(ticker)
    return _record(ticker, "sell", shares, quote.price, quote.as_of.isoformat(),
                   _suggestion_now(ticker) if suggestion is None else suggestion, owner)


def _current_price(ticker: str) -> tuple[float, str, bool]:
    """Latest price, or the last saved close (marked as a fallback) if none can be fetched."""
    try:
        quote = prices.get_latest_price(ticker)
        return quote.price, quote.as_of.isoformat(), False
    except PriceUnavailableError:
        history = storage.load_prices(ticker)
        if history is None or history.empty:
            raise
        return float(history["close"].iloc[-1]), str(history.index[-1].date()), True


def get_portfolio(owner: str = "you") -> Portfolio:
    cash, positions = cash_and_positions(owner)
    results = storage.latest_results()
    holdings = []
    for ticker, position in positions.items():
        price, as_of, fallback = _current_price(ticker)
        value = _money(position.shares * price)
        cost = _money(position.cost)
        suggestion = results.find(ticker) if results else None
        holdings.append(Holding(
            ticker=ticker,
            company_name=universe.company_name(ticker),
            shares=position.shares,
            average_cost=round(position.average_cost, 4),
            current_price=price,
            price_as_of=as_of,
            price_is_fallback=fallback,
            value=value,
            gain=_money(value - cost),
            gain_percent=((value - cost) / cost * 100) if cost else 0.0,
            suggestion=suggestion.action if suggestion else "",
        ))
    holdings.sort(key=lambda h: h.value, reverse=True)
    total = _money(cash + sum(h.value for h in holdings))
    return Portfolio(cash=cash, holdings=holdings, total_value=total)


def get_trades(owner: str = "you") -> list[Trade]:
    return list(reversed(storage.load_trades(owner)))


def get_performance(portfolio: Portfolio | None = None, owner: str = "you") -> Performance:
    account = open_account(owner)
    portfolio = portfolio or get_portfolio(owner)
    spy_price, _, _ = _current_price(load_settings().market_ticker)
    benchmark_value = _money(account.benchmark_shares * spy_price)
    account_gain = (portfolio.total_value / account.starting_cash - 1) * 100
    benchmark_gain = (benchmark_value / account.starting_cash - 1) * 100
    return Performance(
        since=account.opened,
        account_value=portfolio.total_value,
        account_gain_percent=account_gain,
        benchmark_value=benchmark_value,
        benchmark_gain_percent=benchmark_gain,
        ahead_by=account_gain - benchmark_gain,
    )


def _split_ratios(trades: list[Trade]) -> dict[str, list[tuple[datetime, float]]]:
    """For each stock, its recorded splits as (split date, new shares per old share)."""
    ratios: dict[str, list[tuple[datetime, float]]] = {}
    held: dict[str, int] = {}
    for trade in trades:
        before = held.get(trade.ticker, 0)
        if trade.kind == "split" and before > 0:
            ratio = (before + trade.shares) / before
            ratios.setdefault(trade.ticker, []).append((datetime.fromisoformat(trade.price_as_of), ratio))
        held[trade.ticker] = before + (-trade.shares if trade.kind == "sell" else trade.shares)
    return ratios


def get_value_history(owner: str = "you") -> list[dict]:
    """Account value and the S&P 500 comparison at each daily close since the account opened.

    For charts only. Starts with the opening value; today's live value is not
    included (use get_performance for that). Saved closes are adjusted for
    splits, so shares are counted in today's units: shares bought before a
    split are multiplied by its ratio. A stock with no close saved for a day
    uses its last earlier close; days before a stock has any close are skipped.
    """
    account = open_account(owner)
    opened = datetime.fromisoformat(account.opened)
    trades = storage.load_trades(owner)
    rows = [{"time": opened, "account": account.starting_cash, "benchmark": account.starting_cash}]
    market = storage.load_prices(load_settings().market_ticker)
    if market is None:
        return rows

    ratios = _split_ratios(trades)

    def units(trade: Trade) -> float:
        factor = 1.0
        for split_date, ratio in ratios.get(trade.ticker, []):
            if split_date.date() > datetime.fromisoformat(trade.time).date():
                factor *= ratio
        return trade.shares * factor

    closes: dict[str, pd.Series] = {}
    for day, spy_close in market["close"].items():
        close_time = datetime(day.year, day.month, day.day, 16, tzinfo=prices.NEW_YORK)
        if close_time <= opened:
            continue
        cash, _ = _replay(trades, account.starting_cash, until=close_time)
        held: dict[str, float] = {}
        for trade in trades:
            if datetime.fromisoformat(trade.time) >= close_time:
                break
            if trade.kind in ("buy", "sell"):
                sign = 1 if trade.kind == "buy" else -1
                held[trade.ticker] = held.get(trade.ticker, 0.0) + sign * units(trade)
        value = cash
        complete = True
        for ticker, shares in held.items():
            if shares <= 1e-9:
                continue
            if ticker not in closes:
                history = storage.load_prices(ticker)
                closes[ticker] = history["close"] if history is not None else pd.Series(dtype=float)
            known = closes[ticker].loc[:day]
            if known.empty:
                complete = False
                break
            value += shares * float(known.iloc[-1])
        if complete:
            rows.append({"time": close_time, "account": _money(value),
                         "benchmark": _money(account.benchmark_shares * float(spy_close))})
    return rows


def apply_splits(owner: str = "you") -> list[Trade]:
    """Add split entries for stocks owned. Each split is applied only once.

    Extra shares are rounded down to whole shares; for the rare uneven split
    (such as 3-for-2 on an odd number of shares) the fraction is dropped.
    """
    added = []
    trades = storage.load_trades(owner)
    account = open_account(owner)
    tickers = {t.ticker for t in trades if t.kind == "buy"}
    for ticker in sorted(tickers):
        first_buy = min(datetime.fromisoformat(t.time) for t in trades if t.ticker == ticker and t.kind == "buy")
        recorded = {t.price_as_of for t in trades if t.ticker == ticker and t.kind == "split"}
        for split in prices.get_splits(ticker, since=first_buy):
            split_key = split.date.isoformat()
            if split_key in recorded:
                continue
            _, positions = _replay(storage.load_trades(owner), account.starting_cash, until=split.date)
            held = positions[ticker].shares if ticker in positions else 0
            extra = int(held * (split.ratio - 1))
            if extra == 0:
                continue
            # For a split, price_as_of holds the split's date, which also marks it as applied.
            trade = _record(ticker, "split", extra, None, split_key, "", owner)
            added.append(trade)
    return added


def reset(owner: str = "you") -> Account:
    storage.archive_account(owner)
    return open_account(owner)
