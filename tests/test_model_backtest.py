import numpy as np
import pandas as pd
import pytest

from stock_ai import backtest, model, signals
from stock_ai.errors import NotEnoughHistoryError
from tests.conftest import planted_table, random_walk_prices, synthetic_economy


@pytest.fixture(scope="module")
def planted():
    return planted_table(np.random.default_rng(3))


# model.py

def test_probabilities_between_0_and_1(planted):
    trained = model.train(planted)
    probabilities = model.predict_many(trained, planted.iloc[:500])
    assert ((probabilities > 0) & (probabilities < 1)).all()


def test_contributions_add_up_to_the_change_from_the_starting_point(planted):
    trained = model.train(planted)
    for i in [0, 10, 123]:
        probability, contributions = model.predict(trained, planted.iloc[i])
        total = sum(c.effect for c in contributions) / 100
        assert total == pytest.approx(probability - trained.starting_point, abs=1e-9)
        assert [abs(c.effect) for c in contributions] == sorted((abs(c.effect) for c in contributions), reverse=True)
        assert {c.signal for c in contributions} == set(signals.FEATURES)


def test_standardizing_uses_training_rows_only(planted):
    train_rows = planted.iloc[:5000]
    trained = model.train(train_rows)
    assert trained.scaler.mean_ == pytest.approx(train_rows[signals.FEATURES].mean().to_numpy())


def test_too_few_rows_raises(planted):
    with pytest.raises(NotEnoughHistoryError):
        model.train(planted.iloc[:100])


# backtest.py: layout

def test_periods_layout_and_gap():
    dates = pd.bdate_range("2014-01-01", "2023-12-29")
    steps = backtest.periods(dates, horizon=63)
    first_training_end, first_test_start, first_test_end = steps[0]
    assert first_test_start == dates[0] + pd.DateOffset(years=3)
    assert first_test_end == first_test_start + pd.DateOffset(months=6)
    for training_end, test_start, _ in steps:
        between = dates[(dates >= training_end) & (dates < test_start)]
        assert len(between) == 63  # the 63 trading days before the test are left out
    for (_, _, end), (_, next_start, _) in zip(steps, steps[1:]):
        assert end == next_start


def test_no_test_row_is_ever_in_its_own_training_data(planted, monkeypatch):
    seen = []
    real_train = model.train

    def recording_train(rows, features=None):
        seen.append(rows.index.max())
        return real_train(rows, features)
    monkeypatch.setattr(model, "train", recording_train)
    backtest.run_backtest(planted, horizon=63)
    steps = backtest.periods(planted.dropna(subset=["rose"]).index, 63)
    for last_training_day, (training_end, test_start, _) in zip(seen, steps):
        assert last_training_day < training_end < test_start


def test_baseline_is_the_share_that_rose(planted):
    result = backtest.run_backtest(planted, horizon=63)
    tested = planted[(planted.index >= pd.Timestamp(result.tested_from)) &
                     (planted.index <= pd.Timestamp(result.tested_to))]
    assert result.overall_baseline == pytest.approx(tested["rose"].mean())
    assert result.overall_forecasts == len(tested)


# QA section 3: honest backtest and sensible behavior

def random_market_table(seed=11, tickers=25, years=9):
    """Signals and outcomes for stocks whose prices move completely at random."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2012-01-02", periods=252 * years)
    market = random_walk_prices(rng, days, volatility=0.01)
    economy = synthetic_economy(days)
    context = signals.build_context(market, economy)
    frames = []
    for number in range(tickers):
        stock = random_walk_prices(rng, days)
        table = signals.build_signals(stock, market, economy, f"R{number:02d}", context=context)
        frames.append(signals.add_outcomes(table, stock, 63))
    return pd.concat(frames)


@pytest.fixture(scope="module")
def random_table():
    return random_market_table()


def test_random_data_scores_no_better_than_guessing(random_table):
    result = backtest.run_backtest(random_table, horizon=63)
    # A model with no skill can still match "always rise" or "always fall", whichever
    # happened more often, so allow for both.
    best_guess = max(result.overall_baseline, 1 - result.overall_baseline)
    assert result.overall_track_record <= best_guess + 0.02


def test_planted_pattern_is_found(planted):
    result = backtest.run_backtest(planted, horizon=63)
    assert result.overall_track_record > result.overall_baseline + 0.05
    trained = model.train(planted)
    weights = dict(zip(signals.FEATURES, np.abs(trained.classifier.coef_[0])))
    assert max(weights, key=weights.get) == "vs_avg_200"


def test_calibration_probabilities_mean_what_they_say(planted):
    result = backtest.run_backtest(planted, horizon=63)
    for bucket in result.calibration:
        if bucket["forecasts"] >= 1000:
            low, high = [int(x.strip("%")) / 100 for x in bucket["bucket"].split(" to ")]
            assert low - 0.05 <= bucket["rose_share"] <= high + 0.05, bucket
