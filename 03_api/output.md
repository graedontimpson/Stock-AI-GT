# API — Output

Interfaces for phase 1 of the Stock AI Analyzer: how the parts of the program
talk to each other and to outside services.

Revised on 2026-10-20 to add paper trading. The previous version is in the git
history.

Two terms used throughout:

- A **function** is a named piece of code that takes inputs and gives back a
  result.
- To **raise an error** means a function stops and reports a named problem to
  whatever called it, instead of returning a result.

## 1. Internal interfaces

Only the functions below may be called from other files.

### `config.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `load_settings()` | none | `Settings` (section 6) | Never fails. A missing API key is recorded as "not set". |

### `storage.py`

The only file that reads or writes the `data/` folder. It has a load and a
save function for each file in the architecture's storage table, for example
`load_prices(ticker)` and `save_prices(ticker, prices)`. A load returns
nothing if the file does not exist yet. Two need special mention:

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `append_trade(trade)` | `Trade` | nothing | Adds one row to the end of the trade list; never rewrites earlier rows. |
| `archive_account()` | none | nothing | Copies the account files to the archive folder before a reset. |

### `data/universe.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `get_sp500(refresh=False)` | whether to download even if saved today | `Universe` | If the download fails, returns the saved list marked out of date. Raises `DataUnavailableError` if nothing is saved. |
| `is_in_sp500(ticker)` | ticker | yes or no | — |

### `data/prices.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `update_history(tickers)` | list of tickers | nothing; saves new daily rows for each | Tickers that fail are listed in the returned report; the rest are saved. |
| `get_history(ticker)` | ticker | `PriceHistory` from storage | Raises `DataUnavailableError` if nothing is saved. |
| `get_latest_price(ticker)` | ticker | `Quote` | Raises `PriceUnavailableError` if Yahoo cannot be reached or returns no price. Never falls back to an old price, because a trade must not use one. |
| `get_splits(ticker, since)` | ticker; date | list of `Split` since that date | Returns an empty list if Yahoo cannot be reached; checked again next day. |

### `data/economy.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `get_economy(refresh=False)` | whether to download even if saved today | `EconomyData` | If the download fails, returns saved data marked out of date. Raises `DataUnavailableError` if nothing is saved. |

### `signals.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `build_signals(prices, market, economy)` | the stock's `PriceHistory`, SPY's `PriceHistory`, `EconomyData` | `SignalTable` | Raises `NotEnoughHistoryError` if the stock has under 1 year of prices. |
| `add_outcomes(signals, prices)` | `SignalTable`, `PriceHistory` | `SignalTable` with a `rose` column | — |

### `model.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `train(training_table)` | `SignalTable` with outcomes, all stocks combined | a trained model | Raises `NotEnoughHistoryError` if there are too few rows to learn from. |
| `predict(model, latest_signals)` | trained model; the most recent signal row for one stock | probability of rising (0 to 1) and a list of `Contribution` | — |

### `backtest.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `run_backtest(training_table)` | `SignalTable` with outcomes | `BacktestResult` | Raises `NotEnoughHistoryError` if there is too little history for even one test period. |

### `suggestions.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `make_suggestion(ticker, probability, contributions, backtest, volatility)` | the model's output for one stock, plus its backtest and volatility | `Suggestion` | — |
| `top_picks(suggestions, count=10)` | list of `Suggestion` | the top Buys and top Sells | Returns empty lists if nothing qualifies. |

### `pipeline.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `run_daily(refresh=False)` | whether to redo today's work | `DailyResults` | Returns today's saved results if they exist. A problem with one stock does not stop the others; that stock is left out and listed in `skipped`. Raises `DataUnavailableError` only if SPY or economic data cannot be loaded at all. |
| `get_suggestion(ticker)` | ticker | `Suggestion` from today's results | Raises `NotInSP500Error` if the ticker is not on the list. |
| `get_explanation(ticker)` | ticker | `JevExplanation` | Returns today's saved explanation if there is one; otherwise calls `jev.explain` and saves the answer. |

### `account.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `open_account()` | none | `Account` | Creates the account with the starting cash if none exists; otherwise returns the existing one. Raises `PriceUnavailableError` if the SPY price for the comparison cannot be fetched. |
| `buy(ticker, shares)` | ticker; whole number of shares | `Trade` | Raises `NotInSP500Error`, `InvalidSharesError`, `PriceUnavailableError`, or `NotEnoughCashError`. Nothing is recorded if any check fails. |
| `sell(ticker, shares)` | ticker; whole number of shares | `Trade` | Raises `InvalidSharesError`, `PriceUnavailableError`, or `NotEnoughSharesError`. Nothing is recorded if any check fails. |
| `get_portfolio()` | none | `Portfolio` | If a current price cannot be fetched, that holding uses the last saved closing price, marked as such. |
| `get_trades()` | none | list of `Trade`, newest first | — |
| `get_performance()` | none | `Performance` | Same price fallback as `get_portfolio`. |
| `apply_splits()` | none | list of split `Trade` entries added | Called by the daily update for each stock owned. |
| `reset()` | none | `Account` | Archives the current account, then opens a new one. |

### `scorecard.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `record(results)` | `DailyResults` | nothing | Saves each Buy and Sell suggestion once per stock per day. |
| `mark_due()` | none | number of suggestions marked | Marks every suggestion that is now 3 months old. Ones whose price cannot be found are left for the next day. |
| `get_scorecard()` | none | `Scorecard` | — |

### `jev.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `explain(suggestion, shares_owned)` | `Suggestion`; how many shares the user owns | `JevExplanation` | Never raises. If the key is missing or Claude cannot be reached, returns an explanation with status `unavailable` and a reason. |

### Website (`app.py` and `pages/`)

Nothing else calls the website. It calls only `pipeline.py`, `account.py`,
`scorecard.get_scorecard`, and `data/prices.get_history` for charts.

## 2. Shared data shapes

### `Universe`

A table with one row per S&P 500 stock: `ticker`, `company_name`, `sector`
(the industry group, such as "Information Technology"). Also carries
`out_of_date` (yes or no).

### `PriceHistory`

A table with one row per trading day, oldest first.

| Column | Description |
| --- | --- |
| `date` | The trading day |
| `open` | Price at the start of the day |
| `high` | Highest price of the day |
| `low` | Lowest price of the day |
| `close` | Price at the end of the day, adjusted so that stock splits do not show up as false jumps. Used for charts and the account |
| `adj_close` | Close, also adjusted for dividends. Used for the model, backtest, and scorecard |
| `volume` | Number of shares traded |
| `filled` | Yes if this row was filled in for a missing day (see `04_data/output.md`) |

### `Quote`

| Field | Description |
| --- | --- |
| `ticker` | Which stock |
| `price` | The latest price |
| `as_of` | When Yahoo recorded that price; may be about 15 minutes ago |
| `market_open` | Whether the stock market was open at that moment |

### `Split`

| Field | Description |
| --- | --- |
| `ticker`, `date` | Which stock and when |
| `ratio` | New shares per old share, for example 2 for a 2-for-1 split |

### `EconomyData`

A table with one row per day. Figures published monthly are repeated on each
day until the next one is published, starting from the publication date.

| Column | Description | FRED code |
| --- | --- | --- |
| `date` | The day | — |
| `interest_rate` | The US central bank's main interest rate | `DFF` |
| `inflation` | How much consumer prices rose over the past year, in percent | from `CPIAUCSL` |
| `unemployment` | Share of workers without a job, in percent | `UNRATE` |
| `vix` | Market nervousness index; higher means more fear | `VIXCLS` |

### `SignalTable`

A table with one row per stock per trading day. These are the model's inputs.

| Column | Description |
| --- | --- |
| `ticker`, `date` | Which stock and day |
| `change_1m`, `change_3m`, `change_6m` | Price change over the last 1, 3, and 6 months |
| `vs_avg_50`, `vs_avg_200` | How far the price is above or below its 50-day and 200-day moving average |
| `volatility_3m` | How much the price swung day to day over the last 3 months |
| `volume_ratio` | Last month's average volume divided by the last year's |
| `market_change_1m`, `market_change_3m` | SPY change over the last 1 and 3 months |
| `vs_market_3m` | The stock's 3-month change minus SPY's |
| `interest_rate`, `interest_rate_change_3m` | Level and 3-month change |
| `inflation`, `unemployment`, `vix` | As in `EconomyData` |
| `rose` | Added by `add_outcomes`: whether the price was higher 3 months later. Empty for recent days where the future is not yet known. |

### `Contribution`

| Field | Description |
| --- | --- |
| `signal` | Column name from `SignalTable` |
| `label` | Plain-English name, for example "Price change over 3 months" |
| `value` | The signal's value for this stock today |
| `effect` | How many percentage points it moved the probability, up (+) or down (−) |

### `BacktestResult`

| Field | Description |
| --- | --- |
| `overall_track_record` | Share of all forecasts with the right direction |
| `overall_baseline` | Share that would have been right by always guessing "rise" |
| `per_stock` | For each ticker: `track_record`, `baseline`, and number of forecasts |
| `tested_from`, `tested_to` | The period covered |

### `Suggestion`

| Field | Description |
| --- | --- |
| `ticker`, `company_name` | Which stock |
| `as_of` | Date of the latest price used |
| `action` | `buy`, `hold`, or `sell` |
| `probability_up` | Chance of being higher in 3 months, 0 to 1 |
| `confidence` | `low`, `medium`, or `high` (rule below) |
| `risk` | `low`, `medium`, or `high`: whether the stock's volatility is in the bottom, middle, or top third of the S&P 500 |
| `track_record`, `baseline` | From the backtest, for this stock |
| `beats_baseline` | Yes or no; if no, `action` is always `hold` |
| `contributions` | List of `Contribution`, largest effect first |

Confidence rule (starting values):

| Confidence | Probability of rising | Track record above baseline |
| --- | --- | --- |
| High | 70% or more, or 30% or less | by 5 points or more |
| Medium | 65% or more, or 35% or less | by 2 points or more |
| Low | anything else | — |

### `DailyResults`

| Field | Description |
| --- | --- |
| `date` | The day the pipeline ran |
| `suggestions` | One `Suggestion` per scored stock |
| `top_buys`, `top_sells` | Up to 10 each, from `suggestions.top_picks` |
| `backtest` | `BacktestResult` |
| `skipped` | Tickers that could not be scored, each with the reason |

### `Account`

| Field | Description |
| --- | --- |
| `opened` | When the account was opened |
| `starting_cash` | $100,000 by default |
| `benchmark_shares` | How many SPY shares the starting cash would have bought when opened, for the comparison |

### `Trade`

One row in the trade list.

| Field | Description |
| --- | --- |
| `id` | A number that goes up by one with each row |
| `time` | When the trade was placed |
| `ticker` | Which stock |
| `kind` | `buy`, `sell`, or `split` |
| `shares` | Shares bought or sold; for a split, the extra shares received |
| `price` | Price per share; empty for a split |
| `price_as_of` | When Yahoo recorded that price |
| `suggestion_at_time` | The AI's suggestion for that stock when the trade was placed, so the user can later see whether they followed it |

### `Holding`

| Field | Description |
| --- | --- |
| `ticker`, `company_name` | Which stock |
| `shares` | Shares owned |
| `average_cost` | Average price paid per share |
| `current_price`, `price_as_of` | Latest price and when it was recorded |
| `price_is_fallback` | Yes if the last closing price had to be used |
| `value` | Shares times current price |
| `gain`, `gain_percent` | Value minus what was paid, in dollars and percent |
| `suggestion` | Today's `action` for this stock |

### `Portfolio`

| Field | Description |
| --- | --- |
| `cash` | Pretend cash available |
| `holdings` | List of `Holding`, largest value first |
| `total_value` | Cash plus the value of all holdings |

### `Performance`

| Field | Description |
| --- | --- |
| `since` | When the account was opened |
| `account_value`, `account_gain_percent` | Current total value and change since opening |
| `benchmark_value`, `benchmark_gain_percent` | Current value of the SPY comparison and its change |
| `ahead_by` | Account gain percent minus benchmark gain percent; positive means beating the market |

### `Scorecard`

| Field | Description |
| --- | --- |
| `pending` | Suggestions not yet 3 months old |
| `first_due` | When the first suggestion will be marked |
| `buy_right`, `buy_total` | Buy suggestions that were right, out of how many marked |
| `sell_right`, `sell_total` | The same for Sell |
| `by_confidence` | The same counts split by low, medium, and high |
| `avg_buy_change`, `avg_sell_change`, `avg_spy_change` | Average 3-month change in adjusted close of Buy picks, Sell picks, and SPY over the same periods |
| `backtest` | The latest `BacktestResult`, shown until real results exist |

### `JevExplanation`

| Field | Description |
| --- | --- |
| `ticker`, `date` | Which stock and day |
| `status` | `ok` or `unavailable` |
| `why` | Why the suggestion is what it is |
| `stands_out` | What is unusual or worth noticing |
| `could_be_wrong` | What could make the suggestion wrong |
| `reason` | Only when `unavailable`: the message from section 5 |

## 3. Outside services

### Wikipedia

| | |
| --- | --- |
| Requested | The "List of S&P 500 companies" page, once a day at most |
| Returned | A table with ticker, company name, and sector |
| Known limits | Edited by volunteers, so changes to the index can appear a day or two late. A few tickers use a dot (`BRK.B`) where Yahoo uses a dash (`BRK-B`). |
| How failures are handled | Use the saved list, marked out of date. Tickers are converted to Yahoo's form when saved. |

### Yahoo Finance, through `yfinance`

| | |
| --- | --- |
| Requested | Daily history for every S&P 500 stock and SPY (10 years on the first run, new days after that); the latest price when a trade is placed or the portfolio is viewed; split records for stocks owned |
| Returned | Tables of daily prices and volume; a single latest price with its time; a list of splits |
| Known limits | Unofficial and free, so it has no guarantee. Too many requests in a short time are refused, which matters with about 500 stocks. Latest prices can be about 15 minutes old. It occasionally breaks until the library is updated. |
| How failures are handled | History is downloaded in batches with a short pause between them, and a failed batch is retried once. A missing latest price blocks the trade with a clear message rather than using an old price. |

### FRED

| | |
| --- | --- |
| Requested | The four series in `EconomyData`, as downloadable data files |
| Returned | One table per series with a date and a value |
| Known limits | Monthly figures are published weeks late and are sometimes revised afterward. The site uses the figures as they stand today, which makes the backtest slightly optimistic. |
| How failures are handled | Retry once, then use saved data. |

### Claude API, through `anthropic`

| | |
| --- | --- |
| Requested | One request per stock per day, only when the user opens that stock, containing Jev's instructions and the stock's data (section 4) |
| Returned | Jev's explanation as structured text (section 4) |
| Known limits | Costs API credit per request. Needs an internet connection and a valid key. Requests can be refused briefly when sent too quickly. |
| How failures are handled | A refused or failed request is retried once. If it fails again, or the answer does not have the required structure, the explanation is marked `unavailable` and the rest of the page is shown as normal. |

## 4. Jev's contract

### What Jev is sent

1. **Instructions**, the same every time:
   - You explain a paper trading suggestion to a beginner. The money is
     pretend.
   - Use only the data provided. Do not add outside facts or recent news.
   - Explain any finance term the first time you use it.
   - Explain why the suggestion is Buy, Hold, or Sell, but never promise an
     outcome.
   - If the user owns the stock, say what the suggestion means for their
     holding.
   - Answer in the required structure, with 2 to 4 sentences per part.
2. **Data**: the `Suggestion` for one stock, plus `shares_owned`.

### What Jev must return

Exactly three text fields: `why`, `stands_out`, `could_be_wrong`. Anything
else is rejected and treated as a failure.

### Worked example

The numbers are made up to show the shape.

Sent:

```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "as_of": "2026-10-19",
  "action": "buy",
  "probability_up": 0.66,
  "confidence": "medium",
  "risk": "medium",
  "track_record": 0.61,
  "baseline": 0.58,
  "beats_baseline": true,
  "shares_owned": 0,
  "contributions": [
    {"signal": "vs_avg_200", "label": "Price compared with 200-day average", "value": 0.08, "effect": 5.1},
    {"signal": "vs_market_3m", "label": "3-month change compared with the market", "value": 0.04, "effect": 2.3},
    {"signal": "vix", "label": "Market nervousness index", "value": 24.0, "effect": -1.8}
  ]
}
```

Returned:

```json
{
  "why": "The suggestion is Buy because the model gives Apple a 66% chance of being higher in 3 months, above the 60% needed for a Buy. The biggest reason is that the price is 8% above its 200-day average, which is the average price over roughly the last 10 months. Stocks trading above that average have more often kept rising in the past.",
  "stands_out": "Apple has done 4 points better than the overall market over the last 3 months, which also nudged the chance up. The market nervousness index is fairly high at 24, and that pulled it down a little. You don't own any Apple shares yet.",
  "could_be_wrong": "The model's track record for Apple is 61%, only 3 points better than always guessing \"rise\", so roughly 4 in 10 past suggestions were wrong. It only sees prices, volume, and economic figures, so it knows nothing about news or company results."
}
```

## 5. Errors

| Error | When it happens | What the user sees |
| --- | --- | --- |
| `NotInSP500Error` | The ticker is not on the S&P 500 list | "XYZ isn't in the S&P 500. This site only trades S&P 500 stocks." |
| `InvalidSharesError` | Shares is zero, negative, or not a whole number | "Enter a whole number of shares, 1 or more." |
| `NotEnoughCashError` | A buy costs more than the cash available | "That would cost $COST but you have $CASH. Try fewer shares." |
| `NotEnoughSharesError` | Selling more shares than owned | "You own N shares of XYZ, so you can sell up to N." |
| `PriceUnavailableError` | The latest price cannot be fetched for a trade | "We couldn't get a current price for XYZ, so the trade wasn't placed. Try again in a minute." |
| `NotEnoughHistoryError` | A stock has under 1 year of prices | "XYZ hasn't been trading long enough for a suggestion. It needs at least 1 year of prices. You can still trade it." |
| `DataUnavailableError`, with saved data | A download failed but older data exists | "We couldn't download new data, so suggestions are from DATE." |
| `DataUnavailableError`, with no saved data | A download failed and nothing is saved | "We couldn't download stock data. Check your internet connection and try again in a few minutes." |
| Jev unavailable: no key | `ANTHROPIC_API_KEY` is not set | "Jev's explanation is turned off because no API key is set. See the README to add one." |
| Jev unavailable: request failed | Claude could not be reached or the answer was unusable | "Jev's explanation couldn't be loaded right now. The suggestion and numbers are not affected." |

## 6. Settings

In `.env`:

| Variable | Default | Description |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | none | Claude API key. Without it, the site runs with no Jev explanations. |
| `JEV_MODEL` | `claude-opus-5-5` | Which Claude model writes the explanations. |

In `config.py`, changeable without touching other code:

| Setting | Default | Description |
| --- | --- | --- |
| `DATA_DIR` | `data` | Where files are saved |
| `STARTING_CASH` | 100000 | Pretend cash in a new account, in dollars |
| `HORIZON_MONTHS` | 3 | How far ahead suggestions look |
| `BUY_THRESHOLD` | 0.60 | Probability at or above which a stock is a Buy |
| `SELL_THRESHOLD` | 0.40 | Probability at or below which a stock is a Sell |
| `TOP_PICKS` | 10 | How many top Buys and Sells to show |
| `HISTORY_YEARS` | 10 | How much price history to download |
| `MIN_HISTORY_YEARS` | 1 | Shortest history a stock needs for a suggestion |
| `MARKET_TICKER` | `SPY` | The fund used for market trends and the performance comparison |
| `SP500_SOURCE` | Wikipedia "List of S&P 500 companies" page | Where the S&P 500 list comes from |

## 7. Decisions

| Question | Decision | Date |
| --- | --- | --- |
| Confidence rule | Starting values in section 2 | 2026-10-20 |
| Minimum history for a suggestion | 1 year; newer stocks can still be traded but get no suggestion | 2026-10-20 |
| Training companies | Every stock currently in the S&P 500 | 2026-10-20 |
| Economic data revisions | Accepted as a known limit | 2026-10-20 |
| Price for trades | Latest Yahoo price only; never an old price | 2026-10-20 |

No open questions remain.
