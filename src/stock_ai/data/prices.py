"""Yahoo Finance history, latest prices, and splits."""

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from stock_ai import storage
from stock_ai.config import load_settings
from stock_ai.errors import DataUnavailableError, PriceUnavailableError
from stock_ai.shapes import Quote, Split

NEW_YORK = ZoneInfo("America/New_York")
PRICE_COLUMNS = ["open", "high", "low", "close", "adj_close", "volume"]
BATCH_SIZE = 50
FULL_BATCH_SIZE = 20  # 10-year downloads are heavier, so Yahoo gets smaller batches
BATCH_PAUSE_SECONDS = 2
RETRY_PAUSE_SECONDS = 10
RETRY_BATCH_SIZE = 10
MAX_FILLED_GAP = 5
CHANGED_TOLERANCE = 0.0001  # 0.01%
RECENT_PERIOD = "1mo"  # overlaps the saved copy by well over 10 trading days
MAX_STALE_DAYS = 25  # saved history older than this is downloaded in full again
MAX_QUOTE_AGE = timedelta(days=4)


class SkipTicker(Exception):
    """A ticker's data failed a check; it is skipped for the day."""


@dataclass
class UpdateReport:
    updated: list = field(default_factory=list)
    redownloaded: list = field(default_factory=list)
    failed: dict = field(default_factory=dict)  # ticker -> reason


# Downloads (replaced by stand-ins in tests)

def _download(tickers: list[str], period: str) -> dict[str, pd.DataFrame]:
    """Download daily history for several tickers. Returns raw tables by ticker."""
    data = yf.download(
        tickers, period=period, auto_adjust=False, actions=False,
        progress=False, group_by="ticker", threads=True,
    )
    tables = {}
    for ticker in tickers:
        if isinstance(data.columns, pd.MultiIndex):
            if ticker not in data.columns.get_level_values(0):
                continue
            table = data[ticker]
        else:
            table = data
        table = _normalize(table)
        if table["close"].notna().any():  # Yahoo sometimes returns an empty table when busy
            tables[ticker] = table
    return tables


def _normalize(table: pd.DataFrame) -> pd.DataFrame:
    table = table.rename(columns={
        "Open": "open", "High": "high", "Low": "low", "Close": "close",
        "Adj Close": "adj_close", "Volume": "volume",
    })
    table = table[[c for c in PRICE_COLUMNS if c in table.columns]].copy()
    index = pd.to_datetime(table.index)
    if index.tz is not None:
        index = index.tz_localize(None)
    table.index = index.normalize()
    table.index.name = "date"
    return table


def _fetch_quote(ticker: str) -> tuple[float, datetime] | None:
    history = yf.Ticker(ticker).history(period="5d", interval="1m", auto_adjust=False)
    if history is None or history.empty:
        return None
    last = history.dropna(subset=["Close"]).iloc[-1]
    as_of = history.dropna(subset=["Close"]).index[-1].to_pydatetime()
    return float(last["Close"]), as_of


def _fetch_splits(ticker: str) -> pd.Series:
    return yf.Ticker(ticker).splits


# Cleaning

def clean(raw: pd.DataFrame, calendar: pd.DatetimeIndex | None) -> pd.DataFrame:
    """Apply the cleaning rules from 04_data/output.md section 3.

    `calendar` is SPY's trading dates; pass None when cleaning SPY itself.
    Raises SkipTicker if the data fails a check.
    """
    table = raw.dropna(subset=["close"])
    table = table[~table.index.duplicated(keep="last")].sort_index()
    if table.empty:
        raise SkipTicker("no data")
    if (table["close"] <= 0).any() or (table["adj_close"] <= 0).any():
        raise SkipTicker("a price of zero or below")
    table = table.copy()
    table["volume"] = table["volume"].fillna(0)
    table["filled"] = False
    if calendar is None:
        return table

    days = calendar[(calendar >= table.index[0]) & (calendar <= table.index[-1])]
    missing = ~days.isin(table.index)
    if missing.any():
        longest = _longest_run(missing)
        if longest > MAX_FILLED_GAP:
            raise SkipTicker(f"a gap of {longest} trading days")
        table = table.reindex(days)
        filled = table["close"].isna()
        prices = ["open", "high", "low", "close", "adj_close"]
        table[prices] = table[prices].ffill()
        table.loc[filled, "volume"] = 0
        table["filled"] = filled
    table.index.name = "date"
    return table


def _longest_run(flags) -> int:
    longest = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return longest


def _complete_days(table: pd.DataFrame, now: datetime | None = None) -> pd.DataFrame:
    """Drop today's row. Yahoo can still adjust a day's prices in the hours after the
    close, so a day is only saved from the next day on, once it is final."""
    now = (now or datetime.now(NEW_YORK)).astimezone(NEW_YORK)
    return table[table.index < pd.Timestamp(now.date())]


def _differs(saved: pd.DataFrame, recent: pd.DataFrame) -> bool:
    """Whether Yahoo has changed past prices since they were saved."""
    overlap = saved.index.intersection(recent.index)
    if len(overlap) == 0:
        return True
    for column in ["close", "adj_close"]:
        old = saved.loc[overlap, column]
        new = recent.loc[overlap, column]
        if ((new - old).abs() / old.abs() > CHANGED_TOLERANCE).any():
            return True
    return False


# Updating saved history

def _download_batches(tickers: list[str], period: str, progress=None) -> tuple[dict, dict]:
    """Download in batches. Tickers that come back empty get one more try, in smaller
    batches after a longer pause, because Yahoo returns empty tables when it is busy."""
    size = FULL_BATCH_SIZE if period.endswith("y") else BATCH_SIZE
    tables, failed = _download_pass(tickers, period, size, progress)
    retry = [t for t, reason in failed.items() if reason == "no data returned"]
    if retry:
        time.sleep(RETRY_PAUSE_SECONDS)
        if progress:
            progress(f"Trying {len(retry)} stocks again")
        retried, still_failed = _download_pass(retry, period, RETRY_BATCH_SIZE, None)
        tables.update(retried)
        for ticker in retry:
            failed.pop(ticker)
        failed.update(still_failed)
    return tables, failed


def _download_pass(tickers: list[str], period: str, size: int, progress=None) -> tuple[dict, dict]:
    tables, failed = {}, {}
    batches = [tickers[i:i + size] for i in range(0, len(tickers), size)]
    for number, batch in enumerate(batches, start=1):
        if progress:
            progress(f"Downloading prices: batch {number} of {len(batches)}")
        for attempt in range(2):
            try:
                result = _download(batch, period)
                break
            except Exception as error:
                result = None
                reason = f"download failed: {error}"
                if attempt == 0:
                    time.sleep(BATCH_PAUSE_SECONDS)
        if result is None:
            failed.update({ticker: reason for ticker in batch})
        else:
            tables.update(result)
            failed.update({t: "no data returned" for t in batch if t not in result})
        if number < len(batches):
            time.sleep(BATCH_PAUSE_SECONDS)
    return tables, failed


def update_history(tickers: list[str], progress=None) -> UpdateReport:
    """Bring saved history up to date. SPY (the market ticker) is always done first,
    because its dates are the trading calendar used to clean every other ticker."""
    settings = load_settings()
    market = settings.market_ticker
    report = UpdateReport()
    ordered = [market] + [t for t in tickers if t != market]

    def needs_full(ticker):
        saved = storage.load_prices(ticker)
        return saved is None or (pd.Timestamp.today() - saved.index[-1]).days > MAX_STALE_DAYS

    full = [t for t in ordered if needs_full(t)]
    recent = [t for t in ordered if t not in full]

    recent_tables, recent_failed = _download_batches(recent, RECENT_PERIOD, progress)
    report.failed.update(recent_failed)
    for ticker, table in recent_tables.items():
        saved = storage.load_prices(ticker)
        table = _complete_days(table.dropna(subset=["close"]))
        if _differs(saved, table):
            full.append(ticker)
            report.redownloaded.append(ticker)

    full_tables, full_failed = _download_batches(full, f"{settings.history_years}y", progress)
    report.failed.update(full_failed)

    def merged(ticker):
        if ticker in full_tables:
            return _complete_days(full_tables[ticker])
        saved = storage.load_prices(ticker)[PRICE_COLUMNS]
        new = _complete_days(recent_tables[ticker])
        new = new[new.index > saved.index[-1]]
        return pd.concat([saved, new])

    def market_unavailable():
        # Without an up-to-date trading calendar, other tickers can't be cleaned safely,
        # so their saved prices are left exactly as they are.
        if storage.load_prices(market) is None:
            raise DataUnavailableError()
        for ticker in ordered[1:]:
            report.failed.setdefault(ticker, "market data unavailable")
        return report

    if market in report.failed or (market not in full_tables and market not in recent_tables):
        report.failed.setdefault(market, "no data returned")
        return market_unavailable()
    try:
        calendar = clean(merged(market), None).index
    except SkipTicker as reason:
        report.failed[market] = str(reason)
        return market_unavailable()

    for ticker in ordered:
        if ticker in report.failed or (ticker not in full_tables and ticker not in recent_tables):
            continue
        try:
            table = clean(merged(ticker), None if ticker == market else calendar)
        except SkipTicker as reason:
            report.failed[ticker] = str(reason)
            continue
        storage.save_prices(ticker, table)
        report.updated.append(ticker)
    return report


def get_history(ticker: str) -> pd.DataFrame:
    table = storage.load_prices(ticker)
    if table is None:
        raise DataUnavailableError()
    return table


# Latest prices and splits

def market_is_open(moment: datetime) -> bool:
    """Weekdays, 9:30 to 16:00 New York time. Market holidays are not checked."""
    local = moment.astimezone(NEW_YORK)
    opens = local.replace(hour=9, minute=30, second=0, microsecond=0)
    closes = local.replace(hour=16, minute=0, second=0, microsecond=0)
    return local.weekday() < 5 and opens <= local < closes


def get_latest_price(ticker: str, now: datetime | None = None) -> Quote:
    """The latest price. Never falls back to an old saved price."""
    now = now or datetime.now(NEW_YORK)
    try:
        fetched = _fetch_quote(ticker)
    except Exception:
        fetched = None
    if fetched is None:
        raise PriceUnavailableError(ticker)
    price, as_of = fetched
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=NEW_YORK)
    if not price or price <= 0 or now - as_of > MAX_QUOTE_AGE:
        raise PriceUnavailableError(ticker)
    return Quote(ticker=ticker, price=round(price, 4), as_of=as_of, market_open=market_is_open(now))


def get_splits(ticker: str, since: datetime) -> list[Split]:
    """Split records since a moment. An empty list if Yahoo cannot be reached."""
    try:
        splits = _fetch_splits(ticker)
    except Exception:
        return []
    result = []
    for moment, ratio in splits.items():
        moment = pd.Timestamp(moment)
        if moment.tzinfo is None:
            moment = moment.tz_localize(NEW_YORK)
        if moment.to_pydatetime() > since and ratio and ratio > 0:
            result.append(Split(ticker=ticker, date=moment.to_pydatetime(), ratio=float(ratio)))
    return result
