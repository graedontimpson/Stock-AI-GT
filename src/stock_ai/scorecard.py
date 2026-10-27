"""Recording each day's Buy and Sell suggestions, and marking them once they are due."""

from datetime import date

import pandas as pd

from stock_ai import storage
from stock_ai.config import load_settings
from stock_ai.shapes import DailyResults, Scorecard

DUE_CALENDAR_DAYS = 91  # about 63 trading days; only used to show when results are expected


def _adj_close_on(ticker: str, day: str) -> float | None:
    history = storage.load_prices(ticker)
    if history is None:
        return None
    rows = history.loc[history.index <= pd.Timestamp(day)]
    return float(rows["adj_close"].iloc[-1]) if len(rows) else None


def record(results: DailyResults) -> int:
    """Save each Buy and Sell suggestion once per stock per day. Returns how many were added."""
    table = storage.load_scorecard()
    existing = set(zip(table["date"].astype(str), table["ticker"].astype(str)))
    rows = []
    for s in results.suggestions:
        if s.action not in ("buy", "sell") or (s.as_of, s.ticker) in existing:
            continue
        rows.append({
            "date": s.as_of,
            "ticker": s.ticker,
            "action": s.action,
            "probability_up": s.probability_up,
            "confidence": s.confidence,
            "price": _adj_close_on(s.ticker, s.as_of),
            "due": str((pd.Timestamp(s.as_of) + pd.Timedelta(days=DUE_CALENDAR_DAYS)).date()),
            "price_at_due": None,
            "spy_change": None,
            "right": None,
        })
    if rows:
        new = pd.DataFrame(rows, columns=storage.SCORECARD_COLUMNS)
        table = new if table.empty else pd.concat([table, new], ignore_index=True)
        storage.save_scorecard(table)
    return len(rows)


def mark_due() -> int:
    """Mark every suggestion whose horizon has passed. Returns how many were marked."""
    settings = load_settings()
    horizon = settings.horizon_days
    table = storage.load_scorecard()
    if table.empty:
        return 0
    market = storage.load_prices(settings.market_ticker)
    # "right" holds blanks until marked, then True or False, so it must allow both.
    table = table.astype({"right": "object", "price": "float64", "price_at_due": "float64",
                          "spy_change": "float64"})
    marked = 0
    for index, row in table[table["right"].isna()].iterrows():
        history = storage.load_prices(row["ticker"])
        if history is None or market is None:
            continue
        start = pd.Timestamp(row["date"])
        if start not in history.index or start not in market.index:
            continue
        position = history.index.get_loc(start)
        market_position = market.index.get_loc(start)
        if position + horizon >= len(history) or market_position + horizon >= len(market):
            continue  # not due yet, or its price is not available yet
        start_price = history["adj_close"].iloc[position]
        due_price = history["adj_close"].iloc[position + horizon]
        spy_change = market["adj_close"].iloc[market_position + horizon] / market["adj_close"].iloc[market_position] - 1
        rose = due_price > start_price
        table.loc[index, "price"] = start_price
        table.loc[index, "price_at_due"] = due_price
        table.loc[index, "spy_change"] = spy_change
        table.loc[index, "right"] = rose if row["action"] == "buy" else not rose
        marked += 1
    if marked:
        storage.save_scorecard(table)
    return marked


def get_scorecard() -> Scorecard:
    table = storage.load_scorecard()
    done = table[table["right"].notna()].copy()
    pending = table[table["right"].isna()]
    if not done.empty:
        done["right"] = done["right"].astype(str).str.lower().isin(["true", "1", "1.0"])
        done["change"] = done["price_at_due"].astype(float) / done["price"].astype(float) - 1

    def count(frame, action):
        group = frame[frame["action"] == action] if not frame.empty else frame
        return int(group["right"].sum()) if not group.empty else 0, int(len(group))

    def average(frame, action, column="change"):
        group = frame[frame["action"] == action] if not frame.empty else frame
        return float(group[column].astype(float).mean()) if not group.empty else None

    buy_right, buy_total = count(done, "buy")
    sell_right, sell_total = count(done, "sell")
    by_confidence = {}
    for level in ["high", "medium", "low"]:
        group = done[done["confidence"] == level] if not done.empty else done
        by_confidence[level] = {
            "right": int(group["right"].sum()) if not group.empty else 0,
            "total": int(len(group)),
        }
    return Scorecard(
        pending=int(len(pending)),
        first_due=str(pending["due"].min()) if not pending.empty else None,
        buy_right=buy_right,
        buy_total=buy_total,
        sell_right=sell_right,
        sell_total=sell_total,
        by_confidence=by_confidence,
        avg_buy_change=average(done, "buy"),
        avg_sell_change=average(done, "sell"),
        avg_spy_change=float(done["spy_change"].astype(float).mean()) if not done.empty else None,
        backtest=storage.latest_backtest(),
    )
