"""The only module that reads or writes the data/ folder."""

import json
import shutil
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from stock_ai.config import load_settings
from stock_ai.shapes import (
    Account,
    BacktestResult,
    DailyResults,
    JevExplanation,
    Trade,
    from_dict,
    to_dict,
)

TRADE_COLUMNS = ["id", "time", "ticker", "kind", "shares", "price", "price_as_of", "suggestion_at_time"]
SCORECARD_COLUMNS = [
    "date", "ticker", "action", "probability_up", "confidence",
    "price", "due", "price_at_due", "spy_change", "right",
]


def data_dir() -> Path:
    return load_settings().data_dir


def _path(*parts: str) -> Path:
    path = data_dir().joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def saved_today(path: Path) -> bool:
    return path.exists() and date.fromtimestamp(path.stat().st_mtime) == date.today()


def saved_within_days(path: Path, days: int) -> bool:
    return path.exists() and (date.today() - date.fromtimestamp(path.stat().st_mtime)).days < days


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(path)  # replace in one step so a crash never leaves half a file


def _read_json(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


# S&P 500 list

def sp500_path() -> Path:
    return _path("sp500.csv")


def load_sp500() -> pd.DataFrame | None:
    path = sp500_path()
    return pd.read_csv(path) if path.exists() else None


def save_sp500(table: pd.DataFrame) -> None:
    table.to_csv(sp500_path(), index=False)


# Price history

def prices_path(ticker: str) -> Path:
    return _path("prices", f"{ticker}.csv")


def load_prices(ticker: str) -> pd.DataFrame | None:
    path = prices_path(ticker)
    if not path.exists():
        return None
    table = pd.read_csv(path, parse_dates=["date"])
    return table.set_index("date")


def save_prices(ticker: str, prices: pd.DataFrame) -> None:
    prices.rename_axis("date").to_csv(prices_path(ticker))


# Economic indicators

def economy_path() -> Path:
    return _path("economy.csv")


def load_economy() -> pd.DataFrame | None:
    path = economy_path()
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["date"]).set_index("date")


def save_economy(economy: pd.DataFrame) -> None:
    economy.rename_axis("date").to_csv(economy_path())


# Company financials and earnings (phase 2)

def financials_path(ticker: str) -> Path:
    return _path("financials", f"{ticker}.csv")


def load_financials(ticker: str) -> pd.DataFrame | None:
    path = financials_path(ticker)
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["period_end", "filed"])


def save_financials(ticker: str, table: pd.DataFrame) -> None:
    table.to_csv(financials_path(ticker), index=False, date_format="%Y-%m-%d")


def earnings_path(ticker: str) -> Path:
    return _path("earnings", f"{ticker}.csv")


def load_earnings(ticker: str) -> pd.DataFrame | None:
    path = earnings_path(ticker)
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["announced"])


def save_earnings(ticker: str, table: pd.DataFrame) -> None:
    table.to_csv(earnings_path(ticker), index=False)


def load_splits(ticker: str) -> pd.DataFrame | None:
    path = _path("splits", f"{ticker}.csv")
    return pd.read_csv(path, parse_dates=["date"]) if path.exists() else None


def save_splits(ticker: str, table: pd.DataFrame) -> None:
    table.to_csv(_path("splits", f"{ticker}.csv"), index=False, date_format="%Y-%m-%d")


# Account

def load_account() -> Account | None:
    data = _read_json(_path("account", "account.json"))
    return from_dict(Account, data) if data else None


def save_account(account: Account) -> None:
    _write_json(_path("account", "account.json"), to_dict(account))


def load_trades() -> list[Trade]:
    path = _path("account", "trades.csv")
    if not path.exists():
        return []
    table = pd.read_csv(path, dtype={"suggestion_at_time": str, "price_as_of": str}, keep_default_na=False)
    trades = []
    for row in table.to_dict("records"):
        row["id"] = int(row["id"])
        row["shares"] = int(row["shares"])
        row["price"] = float(row["price"]) if row["price"] != "" else None
        trades.append(Trade(**row))
    return trades


def append_trade(trade: Trade) -> None:
    """Add one row to the end of the trade list. Earlier rows are never rewritten."""
    path = _path("account", "trades.csv")
    row = pd.DataFrame([to_dict(trade)], columns=TRADE_COLUMNS)
    row.to_csv(path, mode="a", header=not path.exists(), index=False)


def archive_account() -> None:
    """Copy the account files into account/archive/<time>/ before a reset, then remove them."""
    account_dir = data_dir() / "account"
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    archive = account_dir / "archive" / stamp
    archive.mkdir(parents=True, exist_ok=True)
    for name in ["account.json", "trades.csv"]:
        source = account_dir / name
        if source.exists():
            shutil.copy2(source, archive / name)
            source.unlink()


# Daily results, backtest, and Jev

def load_results(day: str) -> DailyResults | None:
    data = _read_json(_path("results", f"{day}.json"))
    return from_dict(DailyResults, data) if data else None


def save_results(results: DailyResults) -> None:
    _write_json(_path("results", f"{results.date}.json"), to_dict(results))


def latest_results() -> DailyResults | None:
    folder = data_dir() / "results"
    files = sorted(folder.glob("*.json")) if folder.exists() else []
    return load_results(files[-1].stem) if files else None


def latest_backtest() -> BacktestResult | None:
    folder = data_dir() / "backtest"
    files = sorted(folder.glob("*.json")) if folder.exists() else []
    if not files:
        return None
    return from_dict(BacktestResult, _read_json(files[-1]))


def save_backtest(result: BacktestResult) -> None:
    _write_json(_path("backtest", f"{result.run_date}.json"), to_dict(result))


def load_explanations(day: str) -> dict[str, JevExplanation]:
    data = _read_json(_path("jev", f"{day}.json")) or {}
    return {ticker: from_dict(JevExplanation, item) for ticker, item in data.items()}


def save_explanation(explanation: JevExplanation) -> None:
    path = _path("jev", f"{explanation.date}.json")
    data = _read_json(path) or {}
    data[explanation.ticker] = to_dict(explanation)
    _write_json(path, data)


# Scorecard

def load_scorecard() -> pd.DataFrame:
    path = _path("scorecard.csv")
    if not path.exists():
        return pd.DataFrame(columns=SCORECARD_COLUMNS)
    return pd.read_csv(path)


def save_scorecard(table: pd.DataFrame) -> None:
    table[SCORECARD_COLUMNS].to_csv(_path("scorecard.csv"), index=False)
