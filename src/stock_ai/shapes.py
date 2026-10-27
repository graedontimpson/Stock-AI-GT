"""The shared data shapes from the API stage that are records rather than tables.

Tables (Universe, PriceHistory, EconomyData, SignalTable) are pandas
DataFrames; their columns are documented in 03_api/output.md.
"""

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime


def to_dict(record) -> dict:
    return asdict(record)


def from_dict(cls, data: dict):
    """Rebuild a record from a dict, including nested records and lists of them."""
    nested = {
        "contributions": Contribution,
        "suggestions": Suggestion,
        "top_buys": Suggestion,
        "top_sells": Suggestion,
        "backtest": BacktestResult,
        "holdings": Holding,
    }
    values = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        inner = nested.get(f.name)
        if inner is not None and isinstance(value, list):
            value = [from_dict(inner, item) for item in value]
        elif inner is not None and isinstance(value, dict):
            value = from_dict(inner, value)
        values[f.name] = value
    return cls(**values)


@dataclass
class Quote:
    ticker: str
    price: float
    as_of: datetime
    market_open: bool


@dataclass
class Split:
    ticker: str
    date: datetime
    ratio: float


@dataclass
class Contribution:
    signal: str
    label: str
    value: float
    effect: float  # percentage points the signal moved the probability


@dataclass
class BacktestResult:
    overall_track_record: float
    overall_baseline: float
    overall_forecasts: int
    per_stock: dict  # ticker -> {"track_record", "baseline", "forecasts"}
    tested_from: str
    tested_to: str
    run_date: str = ""
    calibration: list = field(default_factory=list)  # [{"bucket", "forecasts", "rose_share"}]


@dataclass
class Suggestion:
    ticker: str
    company_name: str
    as_of: str
    action: str  # "buy", "hold", or "sell"
    probability_up: float
    confidence: str  # "low", "medium", or "high"
    risk: str  # "low", "medium", or "high"
    track_record: float | None
    baseline: float | None
    beats_baseline: bool
    contributions: list = field(default_factory=list)


@dataclass
class DailyResults:
    date: str
    suggestions: list
    top_buys: list
    top_sells: list
    backtest: BacktestResult | None
    skipped: dict  # ticker -> reason

    def find(self, ticker: str) -> Suggestion | None:
        for suggestion in self.suggestions:
            if suggestion.ticker == ticker:
                return suggestion
        return None


@dataclass
class Account:
    opened: str
    starting_cash: float
    benchmark_shares: float
    benchmark_price: float


@dataclass
class Trade:
    id: int
    time: str
    ticker: str
    kind: str  # "buy", "sell", or "split"
    shares: int
    price: float | None
    price_as_of: str
    suggestion_at_time: str


@dataclass
class Holding:
    ticker: str
    company_name: str
    shares: int
    average_cost: float
    current_price: float
    price_as_of: str
    price_is_fallback: bool
    value: float
    gain: float
    gain_percent: float
    suggestion: str


@dataclass
class Portfolio:
    cash: float
    holdings: list
    total_value: float


@dataclass
class Performance:
    since: str
    account_value: float
    account_gain_percent: float
    benchmark_value: float
    benchmark_gain_percent: float
    ahead_by: float


@dataclass
class Scorecard:
    pending: int
    first_due: str | None
    buy_right: int
    buy_total: int
    sell_right: int
    sell_total: int
    by_confidence: dict  # level -> {"right", "total"}
    avg_buy_change: float | None
    avg_sell_change: float | None
    avg_spy_change: float | None
    backtest: BacktestResult | None


@dataclass
class JevExplanation:
    ticker: str
    date: str
    status: str  # "ok" or "unavailable"
    why: str = ""
    stands_out: str = ""
    could_be_wrong: str = ""
    reason: str = ""
