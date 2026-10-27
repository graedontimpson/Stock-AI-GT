"""Walk-forward backtest: train on the past, test on the following period, repeat.

Layout in 04_data/output.md section 5.
"""

from datetime import date

import numpy as np
import pandas as pd

from stock_ai import model
from stock_ai.errors import NotEnoughHistoryError
from stock_ai.shapes import BacktestResult

FIRST_TRAINING_YEARS = 3
TEST_MONTHS = 6
CALIBRATION_BUCKETS = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 1.01]


def periods(dates: pd.DatetimeIndex, horizon: int, first_years: int = FIRST_TRAINING_YEARS,
            test_months: int = TEST_MONTHS) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """(training ends before, test starts, test ends before) for each step.

    Training stops `horizon` trading days before the test starts: those rows'
    outcomes look into the test period, so they are left out (the gap).
    """
    dates = pd.DatetimeIndex(sorted(set(dates)))
    steps = []
    test_start = dates[0] + pd.DateOffset(years=first_years)
    while test_start <= dates[-1]:
        test_end = test_start + pd.DateOffset(months=test_months)
        start_position = dates.searchsorted(test_start)
        if start_position - horizon <= 0:
            break
        training_end = dates[start_position - horizon]
        steps.append((training_end, test_start, test_end))
        test_start = test_end
    return steps


def run_backtest(training_table: pd.DataFrame, horizon: int = 63, gap: bool = True) -> BacktestResult:
    """`training_table` has a date index, a ticker column, the signals, and `rose`.

    `gap=False` exists only for the QA check that proves the gap matters.
    """
    rows = training_table.dropna(subset=["rose"])
    dates = rows.index
    steps = periods(dates, horizon if gap else 0)
    if not steps:
        raise NotEnoughHistoryError()

    tested = []
    for training_end, test_start, test_end in steps:
        if gap:
            train_rows = rows[rows.index < training_end]
        else:
            train_rows = rows[rows.index < test_start]
        test_rows = rows[(rows.index >= test_start) & (rows.index < test_end)]
        if test_rows.empty:
            continue
        try:
            trained = model.train(train_rows)
        except NotEnoughHistoryError:
            continue
        probabilities = model.predict_many(trained, test_rows)
        tested.append(pd.DataFrame({
            "ticker": test_rows["ticker"].to_numpy(),
            "probability": probabilities,
            "rose": test_rows["rose"].to_numpy(),
        }, index=test_rows.index))
    if not tested:
        raise NotEnoughHistoryError()

    results = pd.concat(tested)
    results["right"] = (results["probability"] >= 0.5) == (results["rose"] == 1)

    per_stock = {}
    for ticker, group in results.groupby("ticker"):
        per_stock[ticker] = {
            "track_record": float(group["right"].mean()),
            "baseline": float(group["rose"].mean()),
            "forecasts": int(len(group)),
        }

    calibration = []
    buckets = pd.cut(results["probability"], CALIBRATION_BUCKETS, right=False)
    for bucket, group in results.groupby(buckets, observed=True):
        calibration.append({
            "bucket": f"{bucket.left:.0%} to {min(bucket.right, 1):.0%}",
            "forecasts": int(len(group)),
            "rose_share": float(group["rose"].mean()),
        })

    return BacktestResult(
        overall_track_record=float(results["right"].mean()),
        overall_baseline=float(results["rose"].mean()),
        overall_forecasts=int(len(results)),
        per_stock=per_stock,
        tested_from=str(results.index.min().date()),
        tested_to=str(results.index.max().date()),
        run_date=str(date.today()),
        calibration=calibration,
    )
