"""Run the daily update without opening the site.

    .venv/bin/python scripts/daily_update.py            # skip if already run today
    .venv/bin/python scripts/daily_update.py --refresh  # run again anyway
"""

import sys
import time

from stock_ai import pipeline
from stock_ai.errors import StockAIError


def main():
    started = time.time()
    try:
        results = pipeline.run_daily(refresh="--refresh" in sys.argv, progress=print)
    except StockAIError as error:
        print(error.message)
        sys.exit(1)
    counts = {action: sum(s.action == action for s in results.suggestions) for action in ("buy", "hold", "sell")}
    print(f"\nScored {len(results.suggestions)} stocks in {time.time() - started:.0f}s: "
          f"{counts['buy']} Buy, {counts['hold']} Hold, {counts['sell']} Sell. "
          f"{len(results.skipped)} skipped.")
    if results.backtest:
        b = results.backtest
        print(f"Backtest {b.tested_from} to {b.tested_to}: right {b.overall_track_record:.1%} "
              f"vs always-rise baseline {b.overall_baseline:.1%}.")


if __name__ == "__main__":
    main()
