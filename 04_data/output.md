# Data — Output

Exactly what data phase 1 of the Stock AI Analyzer collects, how it is cleaned
and stored, and how it becomes the model's inputs.

The outside services were checked with `scripts/smoke_check.py` on
2026-10-20. Findings that differ from the original plan are marked
"Checked 2026-10-20" below.

## 1. Datasets

### S&P 500 list

| | |
| --- | --- |
| Source | Wikipedia, "List of S&P 500 companies", first table |
| Requested | The whole table, using `pandas` to read it from the page |
| Kept | Ticker, company name, sector |
| Updated | At most once a day, during the daily update |
| Size | About 503 rows; a few companies have two kinds of shares, each with its own ticker. Checked 2026-10-20: 503 rows, with `BRK.B` and `BF.B` using a dot |

Tickers are converted to Yahoo's form when saved: a dot becomes a dash, so
`BRK.B` becomes `BRK-B`.

### Price history

| | |
| --- | --- |
| Source | Yahoo Finance, through `yfinance` |
| Requested | Daily prices and volume for every ticker on the S&P 500 list, plus SPY |
| Kept | Date, open, high, low, close, adjusted close, volume |
| Updated | Daily update. First run: 10 years per ticker. After that: the last 10 trading days, which overlap what is saved (see section 3) |
| Size | About 2,500 rows per ticker; about 1.3 million rows and roughly 80 MB in total |

Two kinds of closing price are kept:

- **Close** — the price at the end of the day, adjusted for stock splits
  only. Used for charts, the account, and anything the user sees.
- **Adjusted close** — also adjusted for dividends (cash paid out to
  shareholders), so that a dividend payment does not look like a price drop.
  Used for the model, the backtest, and the scorecard, because it measures
  the full return an owner received.

Downloads are made in batches of 50 tickers with a 2-second pause between
batches, to avoid being refused for sending too many requests.

### Latest prices

| | |
| --- | --- |
| Source | Yahoo Finance, through `yfinance` |
| Requested | The most recent price for one ticker, and the time it was recorded |
| Used for | Placing a trade, and valuing holdings on the portfolio page |
| Updated | Each time it is needed. Not saved, except as part of a trade |

### Splits

| | |
| --- | --- |
| Source | Yahoo Finance, through `yfinance` |
| Requested | Split records for each stock the user owns, since the date it was first bought |
| Kept | Date and ratio, added to the trade list as split entries |
| Updated | Daily update |

### Economic indicators

| | |
| --- | --- |
| Source | FRED, downloaded as a CSV file (a plain text table) for each series, from `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<CODE>` |
| Requested | The full history of four series |
| Updated | Daily update |
| Size | A few thousand rows each; under 1 MB in total |
| Checked 2026-10-20 | FRED refuses requests with a custom User-Agent header, so none is sent. The date column is named `observation_date`. Missing values arrive as blanks. CPI and unemployment each have one unpublished month (October 2025). The daily interest rate is usually 2 to 3 business days behind. |

| Code | What it is | How often FRED publishes it |
| --- | --- | --- |
| `DFF` | The US central bank's main interest rate, in percent | Daily |
| `CPIAUCSL` | Consumer price index: the cost of a typical basket of goods | Monthly |
| `UNRATE` | Unemployment rate, in percent | Monthly |
| `VIXCLS` | The VIX: how nervous the market is | Daily |

## 2. Time rules

### Calendar

The **trading calendar** is the list of days the stock market was open. The
site uses SPY's dates as that list. Every table used by the model is lined up
on those dates.

### Dates and times

- Daily data is recorded by trading date (`2026-10-19`), in the market's own
  time zone, New York.
- Moments, such as when a trade was placed or a price was recorded, are
  stored with their time zone, for example `2026-10-19T14:32:05-04:00`, so
  they are never ambiguous.

### No information from the future

A model that accidentally sees the future looks brilliant in a backtest and
fails in real use. This mistake is called **look-ahead**. These rules prevent
it:

- **Prices and volume**: a signal for a given day uses that day's close and
  earlier. Suggestions are made after the market closes, so this is
  information the user really had.
- **Interest rate (`DFF`)**: FRED publishes each day's figure the next
  business day, so a day's signal uses the previous day's figure.
- **VIX**: available at the close, so used on the same day.
- **Monthly figures (`CPIAUCSL`, `UNRATE`)**: published weeks after the month
  they describe. To keep this simple and safe, a month's figure is only used
  from the first trading day of the second month after it. For example, the
  September figure is used from the first trading day of November. This is a
  little later than the real publication date, which costs nothing in
  accuracy that matters and never uses a figure early.
- **Revisions**: FRED's figures are the latest revised versions, not the ones
  first published. Accepted as a known limit in the API stage.
- **S&P 500 membership**: the list is today's, applied to all of history.
  Accepted as a known limit in the architecture stage.

## 3. Cleaning and checks

### S&P 500 list

| Problem | What is done |
| --- | --- |
| The page cannot be read, or its layout has changed | Use the saved list, marked out of date |
| Fewer than 490 or more than 510 tickers | Treat as a broken download; use the saved list |
| Duplicate tickers | Keep one |

### Price history

| Problem | What is done |
| --- | --- |
| Days with no close price | Removed |
| Close or adjusted close of zero or below | The ticker is skipped for the day and listed in `skipped` |
| The same date twice | Keep the last one downloaded |
| Missing trading days (the stock was not traded while SPY was) | Gaps up to 5 days are filled with the previous day's prices and zero volume. Longer gaps: the ticker is skipped and listed in `skipped` |
| A ticker returns no data | Skipped and listed in `skipped`; tried again next day |
| Yahoo changed past prices, because of a new split or dividend | See below |

**Keeping saved history consistent.** When a company splits its stock or pays
a dividend, Yahoo recalculates the adjusted prices for all earlier days. If
the site only added new days to its saved copy, old and new rows would no
longer match. So each daily update downloads the last 10 trading days, which
overlap the saved copy, and compares the overlapping days. If any close or
adjusted close differs by more than 0.01%, the full 10-year history for that
ticker is downloaded again and replaces the saved copy.

### Economic indicators

| Problem | What is done |
| --- | --- |
| Missing values (FRED marks these with a dot) | Removed; the previous value carries forward |
| A series cannot be downloaded | Use the saved copy, marked out of date |

### Latest prices

| Problem | What is done |
| --- | --- |
| No price returned | The trade is refused (`PriceUnavailableError`); the portfolio uses the last saved close, marked as such |
| Price of zero or below | Treated as no price |
| Price recorded more than 4 days ago | Treated as no price, unless the market has been closed since (weekend or holiday) |

## 4. Signals

Definitions used below:

- **P(t)** is a stock's adjusted close on trading day t. **P(t−21)** is 21
  trading days earlier.
- 21 trading days is about 1 month, 63 about 3 months, 126 about 6 months,
  and 252 about 1 year.
- **M(t)** is SPY's adjusted close on day t.
- **Daily return** is the change from one day to the next: P(t) ÷ P(t−1) − 1.

| Signal | In plain words | Formula |
| --- | --- | --- |
| `change_1m` | Price change over about 1 month | P(t) ÷ P(t−21) − 1 |
| `change_3m` | Price change over about 3 months | P(t) ÷ P(t−63) − 1 |
| `change_6m` | Price change over about 6 months | P(t) ÷ P(t−126) − 1 |
| `vs_avg_50` | How far above or below its 50-day average the price is | P(t) ÷ (average of P over the last 50 days) − 1 |
| `vs_avg_200` | The same for the 200-day average | P(t) ÷ (average of P over the last 200 days) − 1 |
| `volatility_3m` | How much the price swung day to day over about 3 months, scaled to a yearly figure | standard deviation of the last 63 daily returns × √252 |
| `volume_ratio` | Whether trading has been busier or quieter than usual | average volume over the last 21 days ÷ average volume over the last 252 days |
| `market_change_1m` | Market change over about 1 month | M(t) ÷ M(t−21) − 1 |
| `market_change_3m` | Market change over about 3 months | M(t) ÷ M(t−63) − 1 |
| `vs_market_3m` | Whether the stock beat the market over about 3 months | `change_3m` − `market_change_3m` |
| `interest_rate` | The central bank rate | `DFF`, as of the previous day |
| `interest_rate_change_3m` | Whether rates went up or down over about 3 months | `interest_rate`(t) − `interest_rate`(t−63) |
| `inflation` | How much prices rose over the past year, in percent | (CPI ÷ CPI 12 months earlier − 1) × 100, using the latest usable month |
| `unemployment` | Unemployment rate, in percent | `UNRATE`, latest usable month |
| `vix` | Market nervousness | `VIXCLS` on day t |

**Standard deviation** is a measure of how spread out a set of numbers is.
Here it measures how much the daily returns bounce around.

A row is only created when every signal has a value. The 200-day average and
the 252-day volume average need about a year of history, which is why a stock
needs at least 1 year of prices to get a suggestion.

### The outcome

| Column | In plain words | Formula |
| --- | --- | --- |
| `rose` | Was the price higher about 3 months later? | yes if P(t+63) > P(t), otherwise no |

The last 63 trading days of every stock have no outcome yet, because their
future has not happened. Those rows are used for today's suggestions but never
for training.

### Before the model sees the signals

The signals are on very different scales: a price change is a small fraction,
while the VIX is a number like 20. Before training, each signal is
**standardized**: rescaled so its average is 0 and a typical distance from
the average is 1. The rescaling is worked out from the training rows only,
then applied unchanged to the test rows and to today's rows.

## 5. Model and backtest data

### Training for today's suggestions

- Rows: every stock currently in the S&P 500, every trading day in the last
  10 years that has all signals and an outcome.
- About 500 stocks × about 2,200 usable days ≈ 1.1 million rows.
- Retrained once a day during the daily update.

### Walk-forward backtest

The backtest is laid out in 6-month test periods:

```
 years:   1    2    3    4    5    6    7    8    9   10
         ├──────────── train ────────────┤gap├ test ┤
         ├─────────────── train ──────────────┤gap├ test ┤
         ├────────────────── train ───────────────┤gap├ test ┤
                                                      ... and so on
```

- The first training period is the first 3 years of usable data.
- Each test period is the next 6 months.
- The window then moves forward 6 months and the model is retrained on
  everything before the new test period.
- **The gap**: each training row's outcome looks 63 trading days ahead. The
  last 63 days before a test period would therefore "know" prices from inside
  the test period. Those 63 days are left out of training for that step.
  Without this gap, the backtest would be falsely optimistic.
- The track record and baseline are calculated from all test periods
  combined, overall and per stock.
- The backtest is rerun once a week rather than daily, because it trains
  about 14 models and its result changes very little from one day to the
  next. The latest result is reused in between.

## 6. Stored files

All in `data/`, which is never committed.

### `sp500.csv`

| Column | Description |
| --- | --- |
| `ticker` | In Yahoo's form, for example `BRK-B` |
| `company_name` | For example "Apple Inc." |
| `sector` | For example "Information Technology" |
| `downloaded` | When the list was downloaded |

Written: daily update, if the download passed its checks.

### `prices/<TICKER>.csv`

One file per ticker, including `SPY.csv`.

| Column | Description | Unit |
| --- | --- | --- |
| `date` | Trading date | — |
| `open`, `high`, `low`, `close` | Prices, adjusted for splits | US dollars |
| `adj_close` | Close, also adjusted for dividends | US dollars |
| `volume` | Shares traded | Shares |
| `filled` | Yes if this row was filled in for a missing day | — |

Written: daily update.

### `economy.csv`

Raw FRED values, one row per date, before the time rules in section 2 are
applied. The time rules are applied when signals are built, so the raw file
stays an exact copy of the source.

| Column | Description | Unit |
| --- | --- | --- |
| `date` | The date FRED gives for the value | — |
| `DFF` | Interest rate | Percent |
| `CPIAUCSL` | Consumer price index | Index points |
| `UNRATE` | Unemployment rate | Percent |
| `VIXCLS` | VIX | Index points |

Written: daily update.

### `account/account.json`

| Field | Description |
| --- | --- |
| `opened` | When the account was opened |
| `starting_cash` | In US dollars |
| `benchmark_shares` | SPY shares the starting cash would have bought |
| `benchmark_price` | The SPY price used |

Written: when an account is opened or reset.

### `account/trades.csv`

One row per trade or split, never rewritten. Columns as `Trade` in the API
stage: `id`, `time`, `ticker`, `kind`, `shares`, `price`, `price_as_of`,
`suggestion_at_time`.

Written: on every buy, sell, and split.

### `account/archive/<DATE>/`

Copies of `account.json` and `trades.csv` as they were before a reset.

### `results/<DATE>.json`

The day's `DailyResults` from the API stage: every suggestion, the top picks,
the latest backtest, and the skipped tickers.

Written: daily update.

### `backtest/<DATE>.json`

The latest `BacktestResult`.

Written: weekly, during the daily update.

### `scorecard.csv`

| Column | Description |
| --- | --- |
| `date` | Day the suggestion was made |
| `ticker` | Which stock |
| `action` | `buy` or `sell` |
| `probability_up` | 0 to 1 |
| `confidence` | `low`, `medium`, or `high` |
| `price` | Adjusted close that day |
| `due` | The trading day 63 trading days later |
| `price_at_due` | Adjusted close on the due day; empty until marked |
| `spy_change` | SPY's change over the same period; empty until marked |
| `right` | Yes or no; empty until marked |

Written: daily update adds the day's rows and fills in any that are due.

### `jev/<DATE>.json`

Every `JevExplanation` made that day, by ticker.

Written: each time a stock page is opened and no explanation is saved yet.

### Total size

About 80 MB after the first run, growing by roughly 10 MB a year. Nothing is
deleted automatically.

## 7. Test data

Tests never download anything or call Claude. They use small sample files in
`tests/fixtures/`, made up by a script rather than copied from Yahoo, so they
can be committed and always give the same results:

| File | Contents |
| --- | --- |
| `sp500.csv` | 3 made-up tickers |
| `prices/*.csv` | 3 years of daily prices for the 3 tickers and SPY, designed to include a split, a missing day, a long gap, and a zero price, so each cleaning rule can be tested |
| `economy.csv` | The same 3 years of all four series, with a few missing values |
| `jev_reply.json` | A correct Jev answer, and a broken one, for testing how answers are checked |

The script that makes them is `scripts/make_fixtures.py`. Running it again
produces identical files.

## 8. Changes to earlier stages

| Stage | Change | Why |
| --- | --- | --- |
| API | `PriceHistory` gains `adj_close` and `filled` | The model and scorecard need the dividend-adjusted price; filled rows must be identifiable |
| API | The scorecard's prices are adjusted closes | Measures the full return, consistent with the model |
| Architecture | The backtest runs weekly, saved in `data/backtest/` | It is slow and changes little day to day |
| Architecture | `scripts/make_fixtures.py` added | Creates the test data |

## 9. Decisions

| Question | Decision | Date |
| --- | --- | --- |
| Backups | No automatic backup in phase 1; copying `data/account/` elsewhere is enough | 2026-10-20 |
| First run | Runs inside the site with a progress message, not as a separate setup step | 2026-10-20 |

No open questions remain.
