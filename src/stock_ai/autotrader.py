"""The AI trader: a separate paper account that trades on the model by itself.

Rules, decided on 2026-10-27:

- It has its own account ("ai"), starting with the same pretend cash as the
  user's. The user's account is never touched.
- Buy when the chance of rising is at or above the Buy threshold (60%); Sell
  at or below the Sell threshold (40%). Unlike the suggestions shown to the
  user, it does not wait for the model to beat the baseline, so its results
  show what following the model would really have done.
- Each Buy uses about 5% of the account's total value (`AI_BUY_FRACTION`), in
  whole shares, and only for stocks it does not own yet. The highest chances
  are bought first. It stops when less than half a Buy's worth of cash is left.
- It sells a whole holding only when that stock reaches Sell; Hold keeps it.
- It runs at most once a day, after the daily scoring, at the latest prices.
"""

from dataclasses import dataclass, field

from stock_ai import account, storage
from stock_ai.config import load_settings
from stock_ai.data import prices
from stock_ai.errors import PriceUnavailableError, StockAIError
from stock_ai.shapes import DailyResults, Suggestion
from stock_ai.suggestions import EPSILON

OWNER = "ai"
AI_BUY_FRACTION = 0.05


@dataclass
class TraderReport:
    day: str
    already_ran: bool = False
    bought: list = field(default_factory=list)  # Trade
    sold: list = field(default_factory=list)  # Trade
    problems: dict = field(default_factory=dict)  # ticker -> message


def rule_action(suggestion: Suggestion) -> str:
    """What the AI trader does with a stock: "buy", "sell", or "hold", from the probability alone."""
    settings = load_settings()
    if suggestion.probability_up + EPSILON >= settings.buy_threshold:
        return "buy"
    if suggestion.probability_up - EPSILON <= settings.sell_threshold:
        return "sell"
    return "hold"


def run(results: DailyResults) -> TraderReport:
    """Place today's trades in the AI account. Does nothing if it already ran today."""
    report = TraderReport(day=results.date)
    if storage.load_ai_last_run() == results.date:
        report.already_ran = True
        return report

    account.open_account(OWNER)
    account.apply_splits(OWNER)
    by_ticker = {s.ticker: s for s in results.suggestions}

    _, positions = account.cash_and_positions(OWNER)
    for ticker, position in sorted(positions.items()):
        suggestion = by_ticker.get(ticker)
        if suggestion is None or rule_action(suggestion) != "sell":
            continue
        try:
            report.sold.append(account.sell(ticker, position.shares, owner=OWNER, suggestion="sell"))
        except StockAIError as error:
            report.problems[ticker] = error.message

    portfolio = account.get_portfolio(OWNER)
    budget = portfolio.total_value * AI_BUY_FRACTION
    cash = portfolio.cash
    owned = {h.ticker for h in portfolio.holdings}
    candidates = sorted((s for s in results.suggestions if rule_action(s) == "buy" and s.ticker not in owned),
                        key=lambda s: s.probability_up, reverse=True)
    for suggestion in candidates:
        amount = min(budget, cash)
        if amount < budget / 2:
            break
        try:
            price = prices.get_latest_price(suggestion.ticker).price
            shares = int(amount // price)
            if shares < 1:
                continue
            trade = account.buy(suggestion.ticker, shares, owner=OWNER, suggestion="buy")
        except (PriceUnavailableError, StockAIError) as error:
            report.problems[suggestion.ticker] = error.message
            continue
        report.bought.append(trade)
        cash -= trade.shares * trade.price

    storage.save_ai_last_run(results.date)
    return report


def describe(report: TraderReport) -> str:
    if report.already_ran:
        return "The AI trader already traded today."
    parts = [f"bought {len(report.bought)}", f"sold {len(report.sold)}"]
    if report.problems:
        parts.append(f"{len(report.problems)} couldn't be traded")
    return "The AI trader " + ", ".join(parts) + "."
