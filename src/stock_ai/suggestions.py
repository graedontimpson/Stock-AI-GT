"""Turning a probability into Buy, Hold, or Sell, with confidence and risk."""

from stock_ai.config import load_settings
from stock_ai.shapes import BacktestResult, Suggestion

# Confidence rule from 03_api/output.md: (probability distance from 50%, points above baseline)
HIGH = (0.20, 0.05)
MEDIUM = (0.15, 0.02)
EPSILON = 1e-9  # so that exactly 0.60 or 0.40 counts as reaching the threshold


def confidence(probability: float, track_record: float | None, baseline: float | None) -> str:
    if track_record is None or baseline is None:
        return "low"
    distance = abs(probability - 0.5)
    edge = track_record - baseline
    for level, (min_distance, min_edge) in (("high", HIGH), ("medium", MEDIUM)):
        if distance + EPSILON >= min_distance and edge + EPSILON >= min_edge:
            return level
    return "low"


def risk_level(volatility: float, cutoffs: tuple[float, float]) -> str:
    """Bottom, middle, or top third of S&P 500 volatility."""
    low_cut, high_cut = cutoffs
    if volatility < low_cut:
        return "low"
    if volatility < high_cut:
        return "medium"
    return "high"


def make_suggestion(ticker: str, company_name: str, as_of: str, probability: float,
                    contributions: list, backtest: BacktestResult | None,
                    volatility: float, volatility_cutoffs: tuple[float, float]) -> Suggestion:
    settings = load_settings()
    stock = (backtest.per_stock.get(ticker) if backtest else None) or {}
    track_record = stock.get("track_record")
    baseline = stock.get("baseline")
    beats = track_record is not None and baseline is not None and track_record > baseline

    if not beats:
        action = "hold"
    elif probability + EPSILON >= settings.buy_threshold:
        action = "buy"
    elif probability - EPSILON <= settings.sell_threshold:
        action = "sell"
    else:
        action = "hold"

    return Suggestion(
        ticker=ticker,
        company_name=company_name,
        as_of=as_of,
        action=action,
        probability_up=probability,
        confidence=confidence(probability, track_record, baseline),
        risk=risk_level(volatility, volatility_cutoffs),
        track_record=track_record,
        baseline=baseline,
        beats_baseline=beats,
        contributions=contributions,
    )


CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def top_picks(suggestions: list[Suggestion], count: int = 10) -> tuple[list, list]:
    """Top Buys (highest probability) and top Sells (lowest), high and medium confidence first."""
    buys = [s for s in suggestions if s.action == "buy"]
    sells = [s for s in suggestions if s.action == "sell"]
    buys.sort(key=lambda s: (CONFIDENCE_ORDER[s.confidence], -s.probability_up))
    sells.sort(key=lambda s: (CONFIDENCE_ORDER[s.confidence], s.probability_up))
    return buys[:count], sells[:count]
