"""The paper trading account.

The trade list is the single source of truth: cash, holdings, and gains are
always worked out from the starting cash plus the trades, never stored.
"""

from dataclasses import dataclass
from datetime import datetime

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


def open_account() -> Account:
    """The existing account, or a new one with the starting cash."""
    account = storage.load_account()
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
    storage.save_account(account)
    return account


def cash_and_positions() -> tuple[float, dict]:
    account = open_account()
    return _replay(storage.load_trades(), account.starting_cash)


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
            suggestion: str) -> Trade:
    trades = storage.load_trades()
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
    storage.append_trade(trade)
    return trade


def buy(ticker: str, shares) -> Trade:
    ticker = ticker.strip().upper()
    shares = _check_shares(shares)
    if not universe.is_in_sp500(ticker):
        raise NotInSP500Error(ticker)
    quote = prices.get_latest_price(ticker)
    cash, _ = cash_and_positions()
    cost = _money(shares * quote.price)
    if cost > cash + 1e-9:
        raise NotEnoughCashError(cost, cash)
    return _record(ticker, "buy", shares, quote.price, quote.as_of.isoformat(), _suggestion_now(ticker))


def sell(ticker: str, shares) -> Trade:
    ticker = ticker.strip().upper()
    shares = _check_shares(shares)
    _, positions = cash_and_positions()
    owned = positions[ticker].shares if ticker in positions else 0
    if shares > owned:
        raise NotEnoughSharesError(ticker, owned)
    quote = prices.get_latest_price(ticker)
    return _record(ticker, "sell", shares, quote.price, quote.as_of.isoformat(), _suggestion_now(ticker))


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


def get_portfolio() -> Portfolio:
    cash, positions = cash_and_positions()
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


def get_trades() -> list[Trade]:
    return list(reversed(storage.load_trades()))


def get_performance(portfolio: Portfolio | None = None) -> Performance:
    account = open_account()
    portfolio = portfolio or get_portfolio()
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


def apply_splits() -> list[Trade]:
    """Add split entries for stocks owned. Each split is applied only once.

    Extra shares are rounded down to whole shares; for the rare uneven split
    (such as 3-for-2 on an odd number of shares) the fraction is dropped.
    """
    added = []
    trades = storage.load_trades()
    account = open_account()
    tickers = {t.ticker for t in trades if t.kind == "buy"}
    for ticker in sorted(tickers):
        first_buy = min(datetime.fromisoformat(t.time) for t in trades if t.ticker == ticker and t.kind == "buy")
        recorded = {t.price_as_of for t in trades if t.ticker == ticker and t.kind == "split"}
        for split in prices.get_splits(ticker, since=first_buy):
            split_key = split.date.isoformat()
            if split_key in recorded:
                continue
            _, positions = _replay(storage.load_trades(), account.starting_cash, until=split.date)
            held = positions[ticker].shares if ticker in positions else 0
            extra = int(held * (split.ratio - 1))
            if extra == 0:
                continue
            # For a split, price_as_of holds the split's date, which also marks it as applied.
            trade = _record(ticker, "split", extra, None, split_key, "")
            added.append(trade)
    return added


def reset() -> Account:
    storage.archive_account()
    return open_account()
