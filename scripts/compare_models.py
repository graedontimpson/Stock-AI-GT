"""Compare the phase 1 model with the phase 1 + phase 2 model on exactly the same rows.

Needs the daily update and the company data download to have run. From the project root:
    .venv/bin/python scripts/compare_models.py

Saves the result to data/backtest/comparison-<DATE>.json. The decision rule is in
06_phase2/output.md section 5.
"""

import json
import time
from datetime import date

from stock_ai import backtest, pipeline, signals, storage
from stock_ai.config import load_settings
from stock_ai.data import economy

MIN_IMPROVEMENT = 0.01  # the phase 2 model must beat phase 1 by at least 1 point


def summary(result):
    low = [b for b in result.calibration if b["bucket"] in ("0% to 30%", "30% to 40%")]
    low_forecasts = sum(b["forecasts"] for b in low)
    low_rose = sum(b["rose_share"] * b["forecasts"] for b in low) / low_forecasts if low_forecasts else None
    return {
        "track_record": result.overall_track_record,
        "baseline": result.overall_baseline,
        "forecasts": result.overall_forecasts,
        "under_40_percent_forecasts": low_forecasts,
        "under_40_percent_rose": low_rose,
        "stocks_beating_baseline_by_2_points": sum(
            s["track_record"] - s["baseline"] >= 0.02 for s in result.per_stock.values()),
        "calibration": result.calibration,
    }


def main():
    settings = load_settings()
    sp500 = storage.load_sp500()
    market = storage.load_prices(settings.market_ticker)
    started = time.time()
    table, skipped = pipeline.build_tables(list(sp500["ticker"]), market, economy.get_economy(),
                                           settings.horizon_days, company=True)
    missing_share = table["financials_missing"].mean()
    print(f"{table['ticker'].nunique()} stocks, {len(table):,} rows; "
          f"{missing_share:.1%} of rows had some company figure filled in.")

    results = {}
    for name, features in [("phase_1", signals.FEATURES), ("phase_2", signals.ALL_FEATURES)]:
        print(f"Backtesting {name} ({len(features)} inputs)...")
        results[name] = summary(backtest.run_backtest(table, settings.horizon_days, features=features))

    one, two = results["phase_1"], results["phase_2"]
    checks = {
        "beats_baseline_overall": two["track_record"] > two["baseline"],
        "beats_phase_1_by_1_point": two["track_record"] - one["track_record"] >= MIN_IMPROVEMENT,
        "better_calibrated_below_40": (two["under_40_percent_rose"] is not None
                                       and two["under_40_percent_rose"] < two["baseline"]),
    }
    report = {
        "date": str(date.today()),
        "rows": len(table),
        "stocks": int(table["ticker"].nunique()),
        "rows_with_filled_company_figures": float(missing_share),
        "results": results,
        "checks": checks,
        "keep_company_inputs": all(checks.values()),
        "seconds": round(time.time() - started),
    }
    path = storage.data_dir() / "backtest" / f"comparison-{date.today()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str))

    print()
    for name, r in results.items():
        low = f"{r['under_40_percent_rose']:.1%}" if r["under_40_percent_rose"] is not None else "n/a"
        print(f"{name}: right {r['track_record']:.1%} vs baseline {r['baseline']:.1%}; "
              f"forecasts under 40% rose {low} of the time ({r['under_40_percent_forecasts']:,}); "
              f"{r['stocks_beating_baseline_by_2_points']} stocks beat their baseline by 2+ points")
    for check, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {check}")
    print(f"\nKeep company inputs: {'yes' if report['keep_company_inputs'] else 'no'}. Saved to {path}")


if __name__ == "__main__":
    main()
