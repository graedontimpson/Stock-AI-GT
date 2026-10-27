import json
from types import SimpleNamespace

import pandas as pd
import pytest

from stock_ai import jev, scorecard, storage
from stock_ai.errors import JEV_FAILED, JEV_NO_KEY
from stock_ai.shapes import Contribution, DailyResults, Suggestion
from tests.conftest import FIXTURES


def suggestion(ticker, action, as_of, probability=0.7, confidence="high"):
    return Suggestion(ticker, ticker, as_of, action, probability, confidence, "low", 0.6, 0.55, True,
                      [Contribution("vs_avg_200", "Price compared with 200-day average", 0.08, 5.1)])


# scorecard.py

def test_records_buys_and_sells_once_per_day(prices_saved):
    day = str(storage.load_prices("AAA").index[100].date())
    results = DailyResults(day, [suggestion("AAA", "buy", day), suggestion("BBB", "sell", day, 0.3),
                                 suggestion("SPY", "hold", day, 0.5)], [], [], None, {})
    assert scorecard.record(results) == 2
    assert scorecard.record(results) == 0
    table = storage.load_scorecard()
    assert set(table["action"]) == {"buy", "sell"}


def test_mark_due(prices_saved):
    history = {t: storage.load_prices(t) for t in ["AAA", "BBB", "SPY"]}
    day = history["AAA"].index[100]
    recent = history["AAA"].index[-10]
    as_of, recent_day = str(day.date()), str(recent.date())
    scorecard.record(DailyResults(as_of, [suggestion("AAA", "buy", as_of), suggestion("BBB", "sell", as_of, 0.3)],
                                  [], [], None, {}))
    scorecard.record(DailyResults(recent_day, [suggestion("AAA", "buy", recent_day)], [], [], None, {}))
    assert scorecard.mark_due() == 2  # the recent one is not due yet

    def change(ticker):
        p = history[ticker]["adj_close"]
        return p.iloc[163] / p.iloc[100] - 1
    card = scorecard.get_scorecard()
    assert card.pending == 1
    assert card.buy_total == 1 and card.sell_total == 1
    assert card.buy_right == int(change("AAA") > 0)
    assert card.sell_right == int(change("BBB") <= 0)
    assert card.avg_buy_change == pytest.approx(change("AAA"))
    assert card.avg_spy_change == pytest.approx(change("SPY"))
    assert card.by_confidence["high"]["total"] == 2


def test_empty_scorecard():
    card = scorecard.get_scorecard()
    assert card.pending == 0 and card.first_due is None and card.buy_total == 0


# jev.py

REPLIES = json.loads((FIXTURES / "jev_replies.json").read_text())


class FakeClaude:
    """Stands in for the Claude client. No real request is ever made in tests."""

    def __init__(self, reply=None, error=None, stop_reason="end_turn"):
        self.requests = []
        self.reply, self.error, self.stop_reason = reply, error, stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self.parse))

    def parse(self, **request):
        self.requests.append(request)
        if self.error:
            raise self.error
        parsed = None
        if self.reply is not None:
            try:
                parsed = jev.JevAnswer.model_validate(self.reply)
            except Exception:
                parsed = None
        return SimpleNamespace(stop_reason=self.stop_reason, parsed_output=parsed)


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")


def test_good_answer(with_key):
    fake = FakeClaude(REPLIES["good"])
    result = jev.explain(suggestion("AAA", "buy", "2024-01-02"), 0, client=fake)
    assert result.status == "ok"
    assert result.why == REPLIES["good"]["why"]
    request = fake.requests[0]
    assert request["model"] == "claude-opus-5-5"
    sent = json.loads(request["messages"][0]["content"])
    assert set(sent) == set(Suggestion.__dataclass_fields__) | {"shares_owned"}


@pytest.mark.parametrize("reply", ["missing_field", "extra_field"])
def test_wrongly_shaped_answer_is_unavailable(with_key, reply):
    result = jev.explain(suggestion("AAA", "buy", "2024-01-02"), 0, client=FakeClaude(REPLIES[reply]))
    assert result.status == "unavailable"
    assert result.reason == JEV_FAILED


def test_failed_request_is_unavailable(with_key):
    result = jev.explain(suggestion("AAA", "buy", "2024-01-02"), 0, client=FakeClaude(error=ConnectionError()))
    assert (result.status, result.reason) == ("unavailable", JEV_FAILED)


def test_refusal_is_unavailable(with_key):
    fake = FakeClaude(REPLIES["good"], stop_reason="refusal")
    assert jev.explain(suggestion("AAA", "buy", "2024-01-02"), 0, client=fake).status == "unavailable"


def test_client_retries_once(with_key):
    assert jev._client("sk-ant-test").max_retries == 1


def test_no_key_makes_no_request():
    fake = FakeClaude(REPLIES["good"])
    result = jev.explain(suggestion("AAA", "buy", "2024-01-02"), 0, client=fake)
    assert (result.status, result.reason) == ("unavailable", JEV_NO_KEY)
    assert fake.requests == []


def test_key_is_never_sent(with_key):
    fake = FakeClaude(REPLIES["good"])
    jev.explain(suggestion("AAA", "buy", "2024-01-02"), 5, client=fake)
    assert "sk-ant-test-not-a-real-key" not in json.dumps(fake.requests[0], default=str)
    assert json.loads(fake.requests[0]["messages"][0]["content"])["shares_owned"] == 5
