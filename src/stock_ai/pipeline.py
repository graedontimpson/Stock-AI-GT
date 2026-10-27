"""The daily update: data, model, suggestions, scorecard, and splits."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from stock_ai import account, backtest, jev, model, scorecard, signals, storage, suggestions
from stock_ai.config import load_settings
from stock_ai.data import economy as economy_data
from stock_ai.data import prices, universe
from stock_ai.errors import DataUnavailableError, NotEnoughHistoryError, NotInSP500Error
from stock_ai.shapes import DailyResults, JevExplanation, Suggestion

BACKTEST_EVERY_DAYS = 7


def _say(progress, message: str) -> None:
    if progress:
        progress(message)


def build_tables(tickers: list[str], market: pd.DataFrame, economy: pd.DataFrame, horizon: int):
    """Signals with outcomes for every ticker, and the reasons any were skipped."""
    context = signals.build_context(market, economy)
    tables, skipped = [], {}
    for ticker in tickers:
        history = storage.load_prices(ticker)
        if history is None:
            skipped.setdefault(ticker, "no saved prices")
            continue
        try:
            table = signals.build_signals(history, market, economy, ticker=ticker, context=context)
        except NotEnoughHistoryError:
            skipped[ticker] = "under 1 year of prices"
            continue
        tables.append(signals.add_outcomes(table, history, horizon))
    if not tables:
        raise DataUnavailableError()
    return pd.concat(tables), skipped


def _backtest_due() -> bool:
    latest = storage.latest_backtest()
    if latest is None or not latest.run_date:
        return True
    return date.fromisoformat(latest.run_date) <= date.today() - timedelta(days=BACKTEST_EVERY_DAYS)


def run_daily(refresh: bool = False, progress=None) -> DailyResults:
    today = str(date.today())
    if not refresh:
        saved = storage.load_results(today)
        if saved is not None:
            return saved

    settings = load_settings()
    _say(progress, "Updating the S&P 500 list")
    sp500 = universe.get_sp500()
    tickers = list(sp500["ticker"])
    names = dict(zip(sp500["ticker"], sp500["company_name"]))

    _say(progress, "Updating prices")
    report = prices.update_history(tickers, progress=progress)
    market = storage.load_prices(settings.market_ticker)
    if market is None:
        raise DataUnavailableError()

    _say(progress, "Updating economic data")
    economy = economy_data.get_economy()

    _say(progress, "Calculating signals")
    table, skipped = build_tables(tickers, market, economy, settings.horizon_days)
    for ticker, reason in report.failed.items():
        if ticker != settings.market_ticker:
            skipped.setdefault(ticker, reason)

    if _backtest_due():
        _say(progress, "Running the weekly backtest (this takes a few minutes)")
        try:
            storage.save_backtest(backtest.run_backtest(table, settings.horizon_days))
        except NotEnoughHistoryError:
            pass  # without a backtest, no stock can beat its baseline, so all are Hold
    backtest_result = storage.latest_backtest()

    _say(progress, "Training the model")
    trained = model.train(table)

    _say(progress, "Scoring every stock")
    latest_day = table.index.max()
    latest_rows = table[table.index == latest_day]
    stale = set(table["ticker"].unique()) - set(latest_rows["ticker"])
    for ticker in stale:
        skipped.setdefault(ticker, "no price for the latest trading day")
    cutoffs = tuple(np.quantile(latest_rows["volatility_3m"], [1 / 3, 2 / 3]))
    scored = []
    for day, row in latest_rows.iterrows():
        probability, contributions = model.predict(trained, row)
        scored.append(suggestions.make_suggestion(
            ticker=row["ticker"],
            company_name=names.get(row["ticker"], row["ticker"]),
            as_of=str(day.date()),
            probability=probability,
            contributions=contributions,
            backtest=backtest_result,
            volatility=float(row["volatility_3m"]),
            volatility_cutoffs=cutoffs,
        ))
    scored.sort(key=lambda s: s.probability_up, reverse=True)
    # A stock whose download failed may still be scored from its saved prices; only
    # stocks that got no suggestion at all count as skipped.
    scored_tickers = {s.ticker for s in scored}
    skipped = {t: reason for t, reason in skipped.items() if t not in scored_tickers}
    top_buys, top_sells = suggestions.top_picks(scored, settings.top_picks)

    results = DailyResults(
        date=today,
        suggestions=scored,
        top_buys=top_buys,
        top_sells=top_sells,
        backtest=backtest_result,
        skipped=skipped,
    )
    storage.save_results(results)

    _say(progress, "Updating the scorecard and checking for stock splits")
    scorecard.record(results)
    scorecard.mark_due()
    if storage.load_account() is not None:
        account.apply_splits()
    return results


def get_suggestion(ticker: str) -> Suggestion | None:
    """Today's (or the latest) suggestion. None if the stock could not be scored."""
    ticker = ticker.strip().upper()
    if not universe.is_in_sp500(ticker):
        raise NotInSP500Error(ticker)
    results = storage.load_results(str(date.today())) or storage.latest_results()
    return results.find(ticker) if results else None


def get_explanation(ticker: str) -> JevExplanation | None:
    """Today's saved explanation, or a new one from Jev (saved only if it worked)."""
    today = str(date.today())
    saved = storage.load_explanations(today).get(ticker)
    if saved is not None:
        return saved
    suggestion = get_suggestion(ticker)
    if suggestion is None:
        return None
    _, positions = account.cash_and_positions() if storage.load_account() else (0, {})
    owned = positions[ticker].shares if ticker in positions else 0
    explanation = jev.explain(suggestion, owned)
    if explanation.status == "ok":
        storage.save_explanation(explanation)
    return explanation
