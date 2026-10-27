"""Settings, and the only place that reads the .env file."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    anthropic_api_key: str | None
    jev_model: str = "claude-opus-5-5"
    sec_contact: str | None = None  # email(s) sent with SEC requests, as the SEC asks
    starting_cash: float = 100_000.0
    horizon_months: int = 3
    horizon_days: int = 63  # trading days in about 3 months
    buy_threshold: float = 0.60
    sell_threshold: float = 0.40
    min_edge: float = 0.02  # points a stock's track record must beat its baseline by
    top_picks: int = 10
    company_inputs: bool = False  # phase 2 inputs; switched on only if they beat phase 1
    history_years: int = 10
    min_history_years: int = 1
    market_ticker: str = "SPY"
    sp500_source: str = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    @property
    def has_api_key(self) -> bool:
        return bool(self.anthropic_api_key)

    def __repr__(self) -> str:
        # Never show the key itself, even when settings are printed.
        key = "set" if self.has_api_key else "not set"
        return f"Settings(data_dir={self.data_dir}, anthropic_api_key={key}, jev_model={self.jev_model})"


def load_settings() -> Settings:
    """Read settings from .env (if present) and the environment, with defaults.

    STOCK_AI_DATA_DIR overrides where data is saved; the tests use it so they
    never touch the real data/ folder.
    """
    file_values = dotenv_values(PROJECT_ROOT / ".env")

    def value(name: str) -> str | None:
        return os.environ.get(name) or file_values.get(name) or None

    data_dir = Path(value("STOCK_AI_DATA_DIR") or PROJECT_ROOT / "data")
    return Settings(
        data_dir=data_dir,
        anthropic_api_key=value("ANTHROPIC_API_KEY"),
        jev_model=value("JEV_MODEL") or Settings.jev_model,
        sec_contact=value("SEC_CONTACT"),
    )
