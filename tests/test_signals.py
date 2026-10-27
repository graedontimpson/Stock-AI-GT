import math

import numpy as np
import pandas as pd
import pytest

from stock_ai import signals
from stock_ai.data import prices
from stock_ai.errors import NotEnoughHistoryError
from tests.conftest import fixture_economy, raw_prices


@pytest.fixture(scope="module")
def inputs():
    market = prices.clean(raw_prices("SPY"), None)
    stock = prices.clean(raw_prices("AAA"), market.index)
    return stock, market, fixture_economy()


def test_every_signal_matches_a_hand_calculation(inputs):
    stock, market, economy = inputs
    table = signals.build_signals(stock, market, economy, ticker="AAA")
    day = stock.index[600]
    row = table.loc[day]
    p = stock["adj_close"]
    m = market["adj_close"]
    i = stock.index.get_loc(day)

    assert row["change_1m"] == pytest.approx(p.iloc[i] / p.iloc[i - 21] - 1)
    assert row["change_3m"] == pytest.approx(p.iloc[i] / p.iloc[i - 63] - 1)
    assert row["change_6m"] == pytest.approx(p.iloc[i] / p.iloc[i - 126] - 1)
    assert row["vs_avg_50"] == pytest.approx(p.iloc[i] / p.iloc[i - 49:i + 1].mean() - 1)
    assert row["vs_avg_200"] == pytest.approx(p.iloc[i] / p.iloc[i - 199:i + 1].mean() - 1)
    daily = p.iloc[i - 63:i + 1].pct_change().dropna()
    assert row["volatility_3m"] == pytest.approx(daily.std() * math.sqrt(252))
    volume = stock["volume"]
    assert row["volume_ratio"] == pytest.approx(volume.iloc[i - 20:i + 1].mean() / volume.iloc[i - 251:i + 1].mean())
    assert row["market_change_1m"] == pytest.approx(m.loc[day] / m.iloc[m.index.get_loc(day) - 21] - 1)
    assert row["vs_market_3m"] == pytest.approx(row["change_3m"] - row["market_change_3m"])

    # Interest rate: the previous calendar day's DFF (strictly before the day).
    dff = economy["DFF"].dropna()
    assert row["interest_rate"] == pytest.approx(dff[dff.index < day].iloc[-1])
    # VIX: the same day's value if there is one.
    vix = economy["VIXCLS"].dropna()
    assert row["vix"] == pytest.approx(vix[vix.index <= day].iloc[-1])


def test_inflation_uses_cpi_from_12_months_earlier(inputs):
    stock, market, economy = inputs
    table = signals.build_signals(stock, market, economy, ticker="AAA")
    day = pd.Timestamp("2024-06-03")  # first trading day of June: latest usable month is April
    cpi = economy["CPIAUCSL"].dropna()
    expected = (cpi[pd.Timestamp("2024-04-01")] / cpi[pd.Timestamp("2023-04-01")] - 1) * 100
    assert table.loc[day, "inflation"] == pytest.approx(expected)


def test_monthly_figure_first_used_two_months_later(inputs):
    stock, market, economy = inputs
    table = signals.build_signals(stock, market, economy, ticker="AAA")
    unrate = economy["UNRATE"].dropna()
    september = unrate[pd.Timestamp("2024-09-01")]
    # Last trading day of October still uses August; first trading day of November uses September.
    assert table.loc[pd.Timestamp("2024-10-31"), "unemployment"] == unrate[pd.Timestamp("2024-08-01")]
    assert table.loc[pd.Timestamp("2024-11-01"), "unemployment"] == september


def test_missing_month_carries_previous_value(inputs):
    stock, market, economy = inputs
    table = signals.build_signals(stock, market, economy, ticker="AAA")
    unrate = economy["UNRATE"].dropna()
    # October 2023 is missing, so December 2023 (when it would have been used) keeps September's.
    assert table.loc[pd.Timestamp("2023-12-01"), "unemployment"] == unrate[pd.Timestamp("2023-09-01")]


def test_no_row_missing_any_signal(inputs):
    stock, market, economy = inputs
    table = signals.build_signals(stock, market, economy, ticker="AAA")
    assert not table[signals.FEATURES].isna().any().any()
    assert table.index[0] >= stock.index[251]  # the 1-year volume average needs 252 days


def test_under_one_year_raises(inputs):
    stock, market, economy = inputs
    with pytest.raises(NotEnoughHistoryError):
        signals.build_signals(stock.iloc[:200], market, economy, ticker="AAA")


def test_outcomes(inputs):
    stock, market, economy = inputs
    table = signals.add_outcomes(signals.build_signals(stock, market, economy, "AAA"), stock, 63)
    p = stock["adj_close"]
    day = table.index[100]
    i = stock.index.get_loc(day)
    assert table.loc[day, "rose"] == float(p.iloc[i + 63] > p.iloc[i])
    assert table["rose"].iloc[-63:].isna().all()
    assert table["rose"].iloc[:-63].notna().all()


# QA section 3: no look-ahead

def test_future_prices_never_change_past_signals(inputs):
    stock, market, economy = inputs
    cutoff = stock.index[550]
    before = signals.build_signals(stock, market, economy, "AAA")

    rng = np.random.default_rng(1)
    scrambled_stock = stock.copy()
    scrambled_market = market.copy()
    for table in (scrambled_stock, scrambled_market):
        later = table.index > cutoff
        for column in ["open", "high", "low", "close", "adj_close", "volume"]:
            table.loc[later, column] = rng.uniform(1, 1000, later.sum())
    scrambled_economy = economy.copy()
    scrambled_economy.loc[scrambled_economy.index > cutoff] = 999.0

    after = signals.build_signals(scrambled_stock, scrambled_market, scrambled_economy, "AAA")
    pd.testing.assert_frame_equal(before.loc[:cutoff], after.loc[:cutoff])


def test_changing_a_months_cpi_has_no_effect_before_it_is_usable(inputs):
    stock, market, economy = inputs
    before = signals.build_signals(stock, market, economy, "AAA")
    changed = economy.copy()
    changed.loc[pd.Timestamp("2024-03-01"), "CPIAUCSL"] *= 1.5
    after = signals.build_signals(stock, market, changed, "AAA")
    first_usable = pd.Timestamp("2024-05-01")
    pd.testing.assert_frame_equal(before.loc[:first_usable - pd.Timedelta(days=1)],
                                  after.loc[:first_usable - pd.Timedelta(days=1)])
    assert before.loc[first_usable, "inflation"] != after.loc[first_usable, "inflation"]
