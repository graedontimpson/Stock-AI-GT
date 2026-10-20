# Architecture — Output

How the Stock AI Analyzer is put together: a personal paper trading website
with AI Buy/Hold/Sell suggestions. Phase 1 is described in detail; phases 2 to
4 are covered in section 11.

Revised on 2026-10-20 to add paper trading. The previous version is in the git
history.

## 1. Overview

The system is one Python program that runs on the user's own computer and
shows a website in their browser. It has eight parts.

```
                 ┌─────────────────────────────────────────┐
                 │  Website (in the browser)               │
                 │  home · stock · portfolio · scorecard   │
                 └──────┬──────────────────────────┬───────┘
                        │                          │
           ┌────────────▼───────────┐   ┌──────────▼──────────┐
           │ Pipeline               │   │ Account             │
           │ (daily scoring)        │   │ (buy, sell, value)  │
           └─┬──────┬──────┬──────┬─┘   └──────────┬──────────┘
             │      │      │      │                │
     ┌───────▼─┐ ┌──▼────┐ ┌▼────┐ ┌▼─────────┐    │
     │ Data    │ │Signals│ │Model│ │Scorecard │    │
     │gathering│ │       │ │     │ │          │    │
     └──┬───┬──┘ └───────┘ └─────┘ └──────────┘    │
        │   │                                      │
 Yahoo  │   │ FRED             ┌──────┐            │
 Finance┘   └                  │ Jev  ├─ Claude API│
        │                      └──────┘            │
     ┌──▼──────────────────────────────────────────▼──┐
     │ Storage (files on the user's computer)         │
     └────────────────────────────────────────────────┘
```

| Part | What it does |
| --- | --- |
| Website | Shows the pages, takes trades, and asks for suggestions. |
| Account | Holds the pretend cash, records trades, and works out holdings and performance. |
| Pipeline | Once a day, updates data, retrains the model, and scores every S&P 500 stock. |
| Data gathering | Downloads the S&P 500 list, prices, volume, and economic data, and saves a copy. Also fetches the latest price when a trade is placed. |
| Signals | Turns raw data into the numbers the model uses, such as "price change over 3 months". |
| Model | Estimates each stock's probability of rising over 3 months and runs the backtest. |
| Scorecard | Records each day's suggestions and later marks them right or wrong. |
| Jev | Sends one stock's results to Claude and returns a plain-English explanation. |

## 2. Technology choices

All free. The only running cost is the Claude API credit Jev uses.

| Part | Choice | Why |
| --- | --- | --- |
| Language | Python 3.11 or newer | Decided in the product stage; the most common language for data work. |
| Website | Streamlit | Builds a web page from plain Python, with no separate HTML or JavaScript to learn. Supports several pages. Runs locally with one command. |
| S&P 500 list | Wikipedia's "List of S&P 500 companies" table, read with `pandas` | Free, kept up to date, and has the ticker, company name, and industry. |
| Prices, volume, latest price | `yfinance` | Free library that downloads Yahoo Finance data. No account needed. |
| Economic indicators | FRED, read with `pandas` | FRED publishes its data as plain downloadable files, so no account or key is needed. |
| Data handling | `pandas` | The standard Python tool for tables of data. |
| Model | `scikit-learn` | The standard beginner-friendly library for this kind of model. |
| Charts | Streamlit's built-in charts | Nothing extra to install. |
| Jev | `anthropic` (official Claude library) | The supported way to call Claude from Python. |
| Secrets | `python-dotenv` | Reads the `.env` file so keys never appear in code. |
| Tests | `pytest` | The standard Python testing tool. |

## 3. Data flow

### Daily scoring

Runs the first time the site is opened each day, or by running
`scripts/daily_update.py`.

1. **Data gathering** updates the S&P 500 list, then downloads any new daily
   prices for every S&P 500 stock and for SPY, plus new economic figures. SPY
   is a fund that tracks the whole S&P 500; it stands in for "the market".
2. **Signals** calculates the model's inputs for every stock and day.
3. **Model** retrains on all S&P 500 stocks, runs the backtest, and scores
   every stock: its probability of rising over 3 months.
4. The pipeline turns each probability into **Buy**, **Hold**, or **Sell**,
   adds the confidence level, and ranks the top Buys and Sells.
5. **Scorecard** saves today's suggestions and marks any from 3 months ago
   as right or wrong.
6. Results are saved. Every page reads from them for the rest of the day.

The very first run downloads 10 years of history for about 500 stocks, which
takes several minutes. After that, each daily update only fetches the newest
days.

### Placing a trade

1. The user enters a ticker and a number of shares and clicks Buy or Sell.
2. **Data gathering** fetches the latest price from Yahoo Finance.
3. **Account** checks the trade is allowed (section 5), records it, and
   updates the cash.
4. The website shows the confirmation and the updated portfolio.

### Viewing a stock

1. The website loads the stock's suggestion from today's saved results.
2. **Jev** is asked for an explanation. Answers are saved, so each stock is
   sent to Claude at most once per day, and only when someone opens it.

## 4. The probability model

### Method

Phase 1 uses **logistic regression**. It is a standard method that takes
several numbers about a stock and outputs a probability between 0% and 100%.
It was chosen because:

- it is the simplest method that produces a real probability;
- it shows how much each input pushed the probability up or down, which is
  what the stock page and Jev need;
- it is less prone than complex methods to "memorizing" the past, a problem
  called **overfitting**, where a model looks accurate on old data but fails
  on new data.

More complex methods can be tried later. They only replace this one if they
beat it in the backtest.

### Inputs

Each is calculated from data available on the day, never from the future.

| Group | Inputs |
| --- | --- |
| Historical prices | Price change over the last 1, 3, and 6 months; price compared with its 50-day and 200-day moving averages (the average price over that many trading days); volatility over the last 3 months |
| Trading volume | Recent volume compared with its usual level |
| Market trends | SPY change over the last 1 and 3 months; the stock's change compared with SPY |
| Economic indicators | Interest rate level and its recent change; inflation rate; unemployment rate; the VIX (a measure of how nervous the market is) |

### What it predicts

For each stock and day: "Will the price be higher in 3 months than it is
today?" The answer in past data is yes or no, and the model learns the link
between the inputs and that answer.

### Training data

One model, trained on about 10 years of daily history for every stock
currently in the S&P 500.

### Backtest

The backtest uses the **walk-forward** approach, which copies how the site
would really have been used:

1. Train the model on data up to a past date.
2. Make forecasts for the following period.
3. Compare them with what actually happened.
4. Move the date forward and repeat.

The model is never tested on data it learned from. The result shown as the
track record is the share of forecasts where the direction was right.

Stocks rise more often than they fall, so always guessing "rise" already
scores above 50%. The track record is therefore shown next to that
**baseline**, and the model only counts as useful if it beats it.

### From probability to suggestion

| Suggestion | Rule |
| --- | --- |
| Buy | Probability of rising 60% or more |
| Sell | Probability of rising 40% or less |
| Hold | Anything in between, or the model did not beat the baseline for this stock |

**Confidence** is low, medium, or high, based on how far the probability is
from 50% and how far the track record is above the baseline. Top picks are the
Buys with the highest probabilities and the Sells with the lowest, high and
medium confidence first.

## 5. The paper trading account

### Rules

- Starts with $100,000 of pretend cash.
- Buy: any stock on today's S&P 500 list, in whole shares, if the cost is no
  more than the cash available.
- Sell: only shares the user owns, in whole shares. Stocks that have left the
  S&P 500 since they were bought can still be sold.
- Price: the latest price from Yahoo Finance at the moment of the trade. If
  it cannot be fetched, the trade is refused rather than using an old price.
- No fees. Trades are allowed at any time; outside market hours they use the
  last closing price.
- Reset: clears all trades and starts again with $100,000. The old account is
  archived, not deleted.

### How it is stored

The **trade list is the single source of truth**. Cash, holdings, and gains
are always worked out from the starting cash plus the list of trades, never
stored separately. This means the account can never drift out of step with
its history.

### Holdings and gains

For each stock owned: shares held, **average cost** (the average price paid
per share), current price, current value, and gain or loss in dollars and
percent.

### Performance against the S&P 500

When the account is opened, the site records what $100,000 would buy in SPY
at that moment. The performance page compares the account's current total
value with the current value of that SPY position. Neither side includes
dividends, so the comparison is fair.

### Stock splits

When a company **splits** its stock (for example, every 1 share becomes 2,
each at half the price), the account would otherwise show a false loss. The
daily update checks Yahoo Finance's split records and adds a split entry to
the trade list for any stock the user owns, adjusting the shares and the
average cost.

## 6. Jev

**Sent to Claude**, per stock:

- the stock's name and ticker;
- the suggestion, probability of rising, confidence, risk level, and the
  track record with its baseline;
- the input values and how much each pushed the probability up or down;
- whether the user owns the stock, and how many shares.

**Returned**: a short explanation with three parts: why the suggestion is
what it is, what stands out, and what could make it wrong.

**Keeping Jev to the page**:

- Jev's instructions tell it to use only the numbers it was sent, explain any
  term it uses, and never promise an outcome.
- Jev receives no raw price tables and has no internet access, so it cannot
  bring in outside facts.
- The same numbers Jev was sent are shown on the page, so the user can check
  every claim.

**Cost control**: Jev is only called when the user opens a stock, and answers
are saved per stock per day. The Claude model name is a setting, so a cheaper
or stronger model can be chosen without changing code.

**If Claude is unavailable**: the page still shows the suggestion, the
numbers, and the chart, with a note that the explanation could not be loaded.

## 7. Scorecard

- Each day, every Buy and Sell suggestion is saved with the date, stock,
  suggestion, probability, and that day's price.
- Once 3 months have passed, each is marked: a Buy is right if the price
  rose, a Sell is right if the price fell.
- The scorecard page shows:
  - the share of Buy and Sell suggestions that were right, overall and by
    confidence level;
  - the average 3-month change of Buy picks, Sell picks, and SPY over the
    same periods, which shows whether following the suggestions would have
    beaten the market.
- Nothing appears until the first suggestions are 3 months old. Until then,
  the page shows the backtest result and a countdown.

## 8. Storage

Everything is saved as files in a `data/` folder on the user's computer. The
folder is listed in `.gitignore`, so it is never committed.

| What | File | Form |
| --- | --- | --- |
| S&P 500 list | `data/sp500.csv` | One table |
| Price and volume history | `data/prices/<TICKER>.csv` | One table per stock and for SPY |
| Economic indicators | `data/economy.csv` | One table |
| Account settings | `data/account/account.json` | Starting cash, opening date, and SPY shares for the comparison |
| Trades | `data/account/trades.csv` | One row per trade or split |
| Archived accounts | `data/account/archive/<DATE>/` | Copies of the two files above, made on reset |
| Daily scores and backtest | `data/results/<DATE>.json` | One file per day |
| Suggestion log | `data/scorecard.csv` | One row per Buy or Sell suggestion |
| Jev explanations | `data/jev/<DATE>.json` | One file per day |
| Daily snapshots (from phase 2) | `data/snapshots/<DATE>/` | One folder per day |

Plain files were chosen over a database because they can be opened and
inspected directly and need no setup.

## 9. Folder layout

```
src/stock_ai/
├── app.py            the website: home page
├── pages/
│   ├── stock.py      one stock: chart, suggestion, Jev, trade box
│   ├── portfolio.py  holdings, trade history, performance
│   └── scorecard.py  how past suggestions turned out
├── config.py         settings and loading of .env
├── storage.py        reading and writing the data/ folder
├── data/
│   ├── universe.py   the S&P 500 list
│   ├── prices.py     Yahoo Finance history, latest prices, and splits
│   └── economy.py    FRED downloads
├── signals.py        model inputs
├── model.py          training and probabilities
├── backtest.py       walk-forward backtest
├── suggestions.py    probability to Buy/Hold/Sell, confidence, top picks
├── pipeline.py       runs the daily scoring
├── account.py        paper trading rules, holdings, performance
├── scorecard.py      recording and marking suggestions
└── jev.py            Claude call and instructions

tests/                one test file per source file, using saved sample data
                      so tests run without internet or API credit

scripts/
├── daily_update.py   run the daily scoring without opening the site
└── run_backtest.py   run the backtest and print the track record

requirements.txt      the libraries to install
data/                 local storage, not committed
```

## 10. Secrets

- The only secret in phase 1 is the Claude API key.
- It lives in `.env` as `ANTHROPIC_API_KEY=<key>`. `.env` is already in
  `.gitignore`.
- `config.py` is the only file that reads it. No other file touches the key,
  and it is never printed, logged, or sent to Jev.
- `.env.example` lists the variable names with no values, so a teammate knows
  what to fill in.
- If the key is missing, the site still runs and shows everything except the
  Jev explanations.

## 11. Later phases

Each phase adds files without reworking phase 1.

| Phase | What is added | Where it plugs in |
| --- | --- | --- |
| 2 | Company financials | New `data/financials.py`; new inputs in `signals.py` |
| 2 | News headlines for Jev | New `data/news.py`; headlines added to what Jev is sent, marked as context |
| 2 | Daily snapshots | New `data/snapshots.py`; `scripts/daily_update.py` saves them each day |
| 3 | Options activity, short interest, institutional holdings | Shown on the stock page and sent to Jev as context; become inputs in `signals.py` once enough snapshots exist and the backtest shows they help |
| 4 | Social media | New `data/social.py`; summarized by Jev as context |

Two rules keep this clean:

- Every data source is its own file with the same shape: download, save, load.
- The model takes whatever inputs `signals.py` produces, so adding an input
  does not change the model code.

## 12. Risks

| Risk | What it means | How it is handled |
| --- | --- | --- |
| The model may not beat the baseline | Prices are close to unpredictable, so the honest result may be "no better than guessing" | The track record and baseline are always shown; a stock gets Hold unless the baseline is beaten; the scorecard shows real results over time |
| Yahoo Finance access can break | `yfinance` is unofficial and sometimes stops working or is rate-limited, and 500 stocks is a lot of requests | Data is saved locally, history downloads happen once a day, and trades are refused with a clear message if no price is available |
| Today's S&P 500 list flatters the backtest | Training only on companies in the index today leaves out ones that dropped out or failed, which makes the past look easier to predict than it was | Stated next to the track record; the scorecard measures real results going forward |
| Economic data arrives late and is revised | Figures such as inflation are published weeks after the month they describe, and sometimes changed later | Each figure is only used from its publication date onward; revisions are accepted as a known limit |
| Stock splits | A split would show as a false loss in the account | Split records are checked daily and applied to holdings |
| Prices are delayed | Yahoo's latest price can be about 15 minutes old | Shown next to every price and trade |
| API cost | Each Jev explanation uses paid credit | Called only when a stock is opened, at most once per stock per day |

## 13. Decisions

| Question | Decision | Date |
| --- | --- | --- |
| Website tool | Streamlit | 2026-10-13 |
| Claude model for Jev | A setting, defaulting to `claude-opus-5-5` | 2026-10-13 |
| Daily snapshots (phase 2) | Saved by `scripts/daily_update.py`, run manually to start | 2026-10-13 |
| Training data | Every stock currently in the S&P 500 (replaces the earlier list of about 50) | 2026-10-20 |
| Market stand-in | SPY, for both market trends and the performance comparison | 2026-10-20 |
| Account storage | Trade list as the single source of truth | 2026-10-20 |
| Economic data revisions | Accepted as a known limit | 2026-10-20 |
