"""Run the walk-forward backtest on the saved data and print the track record.

Needs the daily update to have run at least once. Run from the project root:
    .venv/bin/python scripts/run_backtest.py
"""

from stock_ai import backtest, pipeline, storage
from stock_ai.config import load_settings
from stock_ai.data import economy


def main():
    settings = load_settings()
    sp500 = storage.load_sp500()
    market = storage.load_prices(settings.market_ticker)
    if sp500 is None or market is None:
        print("No saved data yet. Run scripts/daily_update.py first.")
        return
    table, skipped = pipeline.build_tables(list(sp500["ticker"]), market, economy.get_economy(),
                                           settings.horizon_days)
    print(f"{table['ticker'].nunique()} stocks, {len(table):,} rows; {len(skipped)} skipped.")
    result = backtest.run_backtest(table, settings.horizon_days)
    storage.save_backtest(result)
    print(f"Tested {result.tested_from} to {result.tested_to}, {result.overall_forecasts:,} forecasts.")
    print(f"Right {result.overall_track_record:.1%} of the time; "
          f"always guessing 'rise' was right {result.overall_baseline:.1%}.")
    beat = sum(s["track_record"] > s["baseline"] for s in result.per_stock.values())
    print(f"Beat the baseline for {beat} of {len(result.per_stock)} stocks.")
    print("\nCalibration (chance given -> share that actually rose):")
    for bucket in result.calibration:
        print(f"  {bucket['bucket']:>12}: {bucket['rose_share']:.1%} of {bucket['forecasts']:,}")


if __name__ == "__main__":
    main()
