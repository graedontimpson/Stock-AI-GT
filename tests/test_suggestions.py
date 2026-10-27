import pytest

from stock_ai import suggestions
from stock_ai.shapes import BacktestResult


def backtest_for(track_record, baseline):
    return BacktestResult(track_record, baseline, 1000,
                          {"AAA": {"track_record": track_record, "baseline": baseline, "forecasts": 1000}},
                          "2020-01-01", "2024-01-01")


def suggest(probability, track_record=0.62, baseline=0.55, volatility=0.25):
    return suggestions.make_suggestion("AAA", "Alpha", "2024-01-02", probability, [],
                                       backtest_for(track_record, baseline), volatility, (0.2, 0.3))


@pytest.mark.parametrize("probability, action", [
    (0.60, "buy"), (0.59, "hold"), (0.50, "hold"), (0.41, "hold"), (0.40, "sell"), (0.10, "sell"), (0.95, "buy"),
])
def test_thresholds(probability, action):
    assert suggest(probability).action == action


@pytest.mark.parametrize("probability", [0.9, 0.1])
def test_not_beating_baseline_is_always_hold(probability):
    result = suggest(probability, track_record=0.55, baseline=0.55)
    assert result.action == "hold"
    assert result.beats_baseline is False


def test_overall_model_not_beating_baseline_is_always_hold():
    # The stock itself beats its baseline by 10 points, but the model overall does not.
    backtest = BacktestResult(0.57, 0.59, 1000,
                              {"AAA": {"track_record": 0.65, "baseline": 0.55, "forecasts": 1000}},
                              "2020-01-01", "2024-01-01")
    for probability in [0.9, 0.1]:
        result = suggestions.make_suggestion("AAA", "Alpha", "2024-01-02", probability, [], backtest, 0.2, (0.2, 0.3))
        assert result.action == "hold"
        assert result.beats_baseline is False


@pytest.mark.parametrize("track_record, action", [(0.56, "hold"), (0.5699, "hold"), (0.57, "buy"), (0.60, "buy")])
def test_stock_must_beat_its_baseline_by_two_points(track_record, action):
    assert suggest(0.7, track_record=track_record, baseline=0.55).action == action


def test_stock_missing_from_backtest_is_hold():
    result = suggestions.make_suggestion("ZZZ", "Z", "2024-01-02", 0.9, [], backtest_for(0.7, 0.5), 0.2, (0.2, 0.3))
    assert result.action == "hold"
    assert result.confidence == "low"


@pytest.mark.parametrize("probability, track_record, baseline, level", [
    (0.70, 0.60, 0.55, "high"),
    (0.30, 0.60, 0.55, "high"),
    (0.70, 0.59, 0.55, "medium"),  # edge only 4 points
    (0.69, 0.60, 0.55, "medium"),
    (0.65, 0.57, 0.55, "medium"),
    (0.35, 0.57, 0.55, "medium"),
    (0.64, 0.60, 0.55, "low"),
    (0.65, 0.56, 0.55, "low"),  # edge only 1 point
])
def test_confidence_edges(probability, track_record, baseline, level):
    assert suggestions.confidence(probability, track_record, baseline) == level


@pytest.mark.parametrize("volatility, level", [(0.1, "low"), (0.2, "medium"), (0.29, "medium"), (0.3, "high")])
def test_risk_thirds(volatility, level):
    assert suggestions.risk_level(volatility, (0.2, 0.3)) == level


def test_top_picks_order_and_limit():
    picks = [suggest(p) for p in [0.61, 0.75, 0.66, 0.39, 0.25, 0.5]]
    buys, sells = suggestions.top_picks(picks, count=2)
    assert [round(s.probability_up, 2) for s in buys] == [0.75, 0.66]
    assert [round(s.probability_up, 2) for s in sells] == [0.25, 0.39]


def test_top_picks_empty_when_nothing_qualifies():
    assert suggestions.top_picks([suggest(0.5), suggest(0.55)]) == ([], [])
