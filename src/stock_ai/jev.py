"""Jev: a plain-English explanation of one stock's suggestion, written by Claude."""

import json
from datetime import date

import anthropic
from pydantic import BaseModel, ConfigDict

from stock_ai.config import load_settings
from stock_ai.errors import JEV_FAILED, JEV_NO_KEY
from stock_ai.shapes import JevExplanation, Suggestion, to_dict

INSTRUCTIONS = """You explain a paper trading suggestion to a beginner. The money is pretend.

Rules:
- Use only the data provided. Do not add outside facts or recent news.
- Explain any finance term the first time you use it.
- Explain why the suggestion is Buy, Hold, or Sell, but never promise an outcome.
- If the user owns the stock (shares_owned above 0), say what the suggestion means for their holding.
- "probability_up" is the chance of the price being higher in 3 months. "track_record" is how often
  the method was right in past data; "baseline" is how often always guessing "rise" was right.
- In "contributions", "effect" is how many percentage points that input moved the probability.
- Write 2 to 4 sentences for each of the three fields."""


class JevAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    why: str
    stands_out: str
    could_be_wrong: str


def request_data(suggestion: Suggestion, shares_owned: int) -> dict:
    """Exactly what Jev is sent: the Suggestion fields plus shares_owned."""
    data = to_dict(suggestion)
    data["shares_owned"] = shares_owned
    return data


def _client(api_key: str) -> anthropic.Anthropic:
    # One retry on a failed or refused request, as the API stage specifies.
    return anthropic.Anthropic(api_key=api_key, max_retries=1, timeout=120.0)


def explain(suggestion: Suggestion, shares_owned: int = 0, client=None) -> JevExplanation:
    """Never raises: any failure gives an explanation with status "unavailable"."""
    settings = load_settings()
    today = str(date.today())

    def unavailable(reason: str) -> JevExplanation:
        return JevExplanation(ticker=suggestion.ticker, date=today, status="unavailable", reason=reason)

    if not settings.has_api_key:
        return unavailable(JEV_NO_KEY)
    try:
        client = client or _client(settings.anthropic_api_key)
        response = client.beta.messages.parse(
            model=settings.jev_model,
            max_tokens=4000,
            system=INSTRUCTIONS,
            messages=[{
                "role": "user",
                "content": json.dumps(request_data(suggestion, shares_owned), indent=2),
            }],
            output_format=JevAnswer,
            output_config={"effort": "medium"},
            # If a safety check declines the request, the API retries it on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal" or response.parsed_output is None:
            return unavailable(JEV_FAILED)
        answer = JevAnswer.model_validate(response.parsed_output.model_dump())
    except Exception:
        return unavailable(JEV_FAILED)
    return JevExplanation(
        ticker=suggestion.ticker,
        date=today,
        status="ok",
        why=answer.why,
        stands_out=answer.stands_out,
        could_be_wrong=answer.could_be_wrong,
    )
