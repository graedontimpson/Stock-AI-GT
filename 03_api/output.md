# API — Output

Interfaces for phase 1 of the Stock AI Analyzer: how the parts of the program
talk to each other and to outside services.

Two terms used throughout:

- A **function** is a named piece of code that takes inputs and gives back a
  result.
- To **raise an error** means a function stops and reports a named problem to
  whatever called it, instead of returning a result.

## 1. Internal interfaces

Files are listed in the order the pipeline uses them. Only the functions below
may be called from other files.

### `config.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `load_settings()` | none | `Settings` (section 6) | Never fails. A missing API key is recorded as "not set". |

### `storage.py`

The only file that reads or writes the `data/` folder.

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `load_watchlist()` | none | `Watchlist` | Returns an empty watchlist with the default horizon if no file exists. |
| `save_watchlist(watchlist)` | `Watchlist` | nothing | Raises `InvalidWatchlistError` if it has more than 10 tickers or a duplicate. |
| `load_prices(ticker)` | ticker | `PriceHistory`, or nothing if not saved | — |
| `save_prices(ticker, prices)` | ticker, `PriceHistory` | nothing | — |
| `load_economy()` | none | `EconomyData`, or nothing if not saved | — |
| `save_economy(economy)` | `EconomyData` | nothing | — |
| `load_results(date)` | date | `DailyResults`, or nothing if not saved | — |
| `save_results(results)` | `DailyResults` | nothing | — |
| `load_explanations(date)` | date | list of `JevExplanation`, or an empty list | — |
| `save_explanation(explanation)` | `JevExplanation` | nothing | — |

### `data/prices.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `get_prices(ticker, refresh=False)` | ticker; whether to download even if saved data is current | `PriceHistory` | Raises `UnknownTickerError` if Yahoo has no such ticker. Raises `DataUnavailableError` if the download fails and nothing is saved. If the download fails but older data is saved, returns the saved data marked as out of date. |

Saved data is current if its latest row is the most recent trading day.

### `data/economy.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `get_economy(refresh=False)` | whether to download even if saved data is current | `EconomyData` | Same rules as `get_prices`, without the unknown-ticker case. |

### `signals.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `build_signals(prices, market, economy)` | the stock's `PriceHistory`, the S&P 500's `PriceHistory`, `EconomyData` | `SignalTable` | Raises `NotEnoughHistoryError` if the stock has under 1 year of prices. |
| `add_outcomes(signals, prices, horizon)` | `SignalTable`, `PriceHistory`, horizon | `SignalTable` with a `rose` column | — |

### `model.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `train(training_table)` | `SignalTable` with outcomes, for all training stocks combined | a trained model | Raises `NotEnoughHistoryError` if there are too few rows to learn from. |
| `predict(model, latest_signals)` | trained model; the most recent signal row for one stock | probability of rising (0 to 1) and a list of `Contribution` | — |

### `backtest.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `run_backtest(training_table, horizon)` | `SignalTable` with outcomes; horizon | `BacktestResult` | Raises `NotEnoughHistoryError` if there is too little history for even one test period. |

### `jev.py`

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `explain(stock_result)` | `StockResult` | `JevExplanation` | Never raises. If the key is missing or Claude cannot be reached, returns an explanation with status `unavailable` and a reason. |

### `pipeline.py`

The only file the website calls.

| Function | Inputs | Returns | On failure |
| --- | --- | --- | --- |
| `run(watchlist, refresh=False)` | `Watchlist`; whether to redo today's work | `DailyResults` | A problem with one stock does not stop the others. That stock appears in the results with an error message instead of a probability. Raises `DataUnavailableError` only if market or economic data cannot be loaded at all. |
| `get_explanation(stock_result)` | `StockResult` | `JevExplanation` | Returns today's saved explanation if there is one; otherwise calls `jev.explain` and saves the answer. |

### `app.py`

The website. Nothing else calls it. It calls only `pipeline.py`,
`storage.load_watchlist`, and `storage.save_watchlist`.

## 2. Shared data shapes

### `Watchlist`

| Field | Description |
| --- | --- |
| `tickers` | List of up to 10 ticker symbols, in capitals, no duplicates |
| `horizon_months` | 1, 3, or 6 |

### `PriceHistory`

A table with one row per trading day, oldest first.

| Column | Description |
| --- | --- |
| `date` | The trading day |
| `open` | Price at the start of the day |
| `high` | Highest price of the day |
| `low` | Lowest price of the day |
| `close` | Price at the end of the day, adjusted so that stock splits and dividend payments do not show up as false jumps |
| `volume` | Number of shares traded |

It also carries `ticker`, `company_name`, and `out_of_date` (yes or no).

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
| `market_change_1m`, `market_change_3m` | S&P 500 change over the last 1 and 3 months |
| `vs_market_3m` | The stock's 3-month change minus the S&P 500's |
| `interest_rate`, `interest_rate_change_3m` | Level and 3-month change |
| `inflation`, `unemployment`, `vix` | As in `EconomyData` |
| `rose` | Added by `add_outcomes`: whether the price was higher at the end of the horizon. Empty for recent days where the future is not yet known. |

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
| `horizon_months` | Which horizon was tested |
| `overall_track_record` | Share of all forecasts with the right direction |
| `overall_baseline` | Share that would have been right by always guessing "rise" |
| `per_stock` | For each ticker: `track_record`, `baseline`, and number of forecasts |
| `tested_from`, `tested_to` | The period covered |

### `StockResult`

| Field | Description |
| --- | --- |
| `ticker`, `company_name` | Which stock |
| `as_of` | Date of the latest price used |
| `horizon_months` | 1, 3, or 6 |
| `probability_up` | 0 to 1 |
| `risk` | `low`, `medium`, or `high`: whether the stock's volatility is in the bottom, middle, or top third of the training stocks |
| `track_record`, `baseline` | From the backtest, for this stock |
| `beats_baseline` | Yes or no |
| `category` | `riser`, `faller`, or `none` (section 6 thresholds; always `none` if the baseline is not beaten) |
| `confidence` | `low`, `medium`, or `high` (rule below) |
| `contributions` | List of `Contribution`, largest effect first |
| `out_of_date` | Yes if saved data had to be used because a download failed |
| `error` | Empty, or the message from section 5 if this stock could not be processed |

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
| `horizon_months` | 1, 3, or 6 |
| `stocks` | List of `StockResult`, highest probability first |
| `backtest` | `BacktestResult` |

### `JevExplanation`

| Field | Description |
| --- | --- |
| `ticker`, `date`, `horizon_months` | Which stock, day, and horizon |
| `status` | `ok` or `unavailable` |
| `why` | Why the stock scored as it did |
| `stands_out` | What is unusual or worth noticing |
| `could_be_wrong` | What could make the forecast wrong |
| `reason` | Only when `unavailable`: the message from section 5 |

## 3. Outside services

### Yahoo Finance, through `yfinance`

| | |
| --- | --- |
| Requested | About 10 years of daily price history for each watchlist ticker, each built-in training ticker, and the S&P 500 (`^GSPC`); the company name for each ticker |
| Returned | A table of daily open, high, low, close, and volume |
| Known limits | Unofficial and free, so it has no guarantee. Too many requests in a short time are refused. It occasionally breaks until the library is updated. |
| How failures are handled | Tickers are downloaded in one batch, once a day at most. A failed download is retried once, then saved data is used and marked out of date. |

### FRED

| | |
| --- | --- |
| Requested | The four series in `EconomyData`, as downloadable data files |
| Returned | One table per series with a date and a value |
| Known limits | Monthly figures are published weeks late and are sometimes revised afterward. The site uses the figures as they stand today, which makes the backtest slightly optimistic. |
| How failures are handled | Same as Yahoo Finance: retry once, then use saved data. |

### Claude API, through `anthropic`

| | |
| --- | --- |
| Requested | One request per stock per day, containing Jev's instructions and the stock's data (section 4) |
| Returned | Jev's explanation as structured text (section 4) |
| Known limits | Costs API credit per request. Needs an internet connection and a valid key. Requests can be refused briefly when sent too quickly. |
| How failures are handled | A refused or failed request is retried once. If it fails again, or the answer does not have the required structure, the explanation is marked `unavailable` and the rest of the page is shown as normal. |

## 4. Jev's contract

### What Jev is sent

1. **Instructions**, the same every time:
   - You explain a stock forecast to a beginner.
   - Use only the data provided. Do not add outside facts or recent news.
   - Explain any finance term the first time you use it.
   - Do not tell the reader to buy, sell, or hold, and do not promise an
     outcome.
   - Answer in the required structure, with 2 to 4 sentences per part.
2. **Data**: the `StockResult` for one stock, without the `error` and
   `out_of_date` fields.

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
  "as_of": "2026-10-12",
  "horizon_months": 3,
  "probability_up": 0.66,
  "risk": "medium",
  "track_record": 0.61,
  "baseline": 0.58,
  "beats_baseline": true,
  "category": "riser",
  "confidence": "medium",
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
  "why": "The model gives Apple a 66% chance of being higher in 3 months. The biggest reason is that the price is 8% above its 200-day average, which is the average price over roughly the last 10 months. Stocks trading above that average have more often kept rising in the past.",
  "stands_out": "Apple has done 4 points better than the overall market over the last 3 months, which also nudged the probability up. The market nervousness index is fairly high at 24, and that pulled the probability down a little.",
  "could_be_wrong": "The model's track record for Apple is 61%, only 3 points better than always guessing \"rise\", so roughly 4 in 10 past forecasts were wrong. It only sees prices, volume, and economic figures, so it knows nothing about news or company results."
}
```

## 5. Errors

| Error | When it happens | What the user sees |
| --- | --- | --- |
| `UnknownTickerError` | Yahoo has no stock with that symbol | "We couldn't find a stock with the symbol XYZ. Check the spelling and try again." |
| `InvalidWatchlistError` | More than 10 tickers, or the same one twice | "A watchlist can hold up to 10 different stocks." |
| `NotEnoughHistoryError` | A stock has under 1 year of prices | "XYZ hasn't been trading long enough to forecast. It needs at least 1 year of prices." |
| `DataUnavailableError`, with saved data | A download failed but older data exists | "We couldn't download new data, so this page uses data from DATE." |
| `DataUnavailableError`, with no saved data | A download failed and nothing is saved | "We couldn't download stock data. Check your internet connection and try again in a few minutes." |
| Jev unavailable: no key | `ANTHROPIC_API_KEY` is not set | "Jev's explanation is turned off because no API key is set. See the README to add one." |
| Jev unavailable: request failed | Claude could not be reached or the answer was unusable | "Jev's explanation couldn't be loaded right now. The numbers on this page are not affected." |

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
| `HISTORY_YEARS` | 10 | How much price history to download |
| `MIN_HISTORY_YEARS` | 1 | Shortest history a stock needs to be forecast |
| `MAX_WATCHLIST` | 10 | Most tickers on a watchlist |
| `DEFAULT_HORIZON_MONTHS` | 3 | Horizon used on first visit |
| `RISER_THRESHOLD` | 0.60 | Probability at or above which a stock is a likely riser |
| `FALLER_THRESHOLD` | 0.40 | Probability at or below which a stock is a likely faller |
| `MARKET_TICKER` | `^GSPC` | The index used for market trends |
| `TRAINING_TICKERS` | built-in list of about 50 | The companies the model also learns from |

## 7. Open questions

1. **Confidence rule** — are the starting values in section 2 acceptable
   (high at 70% / 30% with a 5-point edge, medium at 65% / 35% with a 2-point
   edge)? They are settings in spirit and will likely be tuned once real
   results are visible.
2. **Minimum history** — a stock needs 1 year of prices to be forecast.
   Recently listed companies are refused with a message. Acceptable?
3. **Training company list** — which roughly 50 companies. Proposed: the 50
   largest US companies by value today, chosen once and written into the
   settings. To be listed in the data stage.
4. **Economic data revisions** — FRED figures are used as they stand today,
   not as first published, which makes the backtest slightly optimistic.
   Tracking original figures is possible but much more work. Accept this as a
   known limit?
