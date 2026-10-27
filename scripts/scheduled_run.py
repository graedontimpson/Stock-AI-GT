"""What the automatic weekday run does. Output goes to data/logs/<DATE>.log.

Run by the launch agent that scripts/schedule.py installs. Can also be run by hand:
    .venv/bin/python scripts/scheduled_run.py
"""

import sys
import time
import traceback
from datetime import date, datetime

from stock_ai import pipeline, storage
from stock_ai.errors import StockAIError


def main():
    logs = storage.data_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / f"{date.today()}.log"
    with open(log_path, "a") as log:
        def say(message):
            log.write(f"{datetime.now():%H:%M:%S} {message}\n")
            log.flush()

        say("Automatic run started")
        started = time.time()
        failed = False
        try:
            results = pipeline.run_daily(progress=say)
            say(f"Daily update done: {len(results.suggestions)} stocks scored, "
                f"{len(results.skipped)} skipped, prices up to "
                f"{results.suggestions[0].as_of if results.suggestions else 'none'}")
        except StockAIError as error:
            failed = True
            say(f"Daily update stopped: {error.message}")
        except Exception:
            failed = True
            say("Daily update failed with an unexpected error:\n" + traceback.format_exc())
        say(f"Automatic run finished in {time.time() - started:.0f}s")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
