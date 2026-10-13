# Architecture — Output

How the Stock AI Analyzer is put together. Phase 1 is described in detail;
phases 2 to 4 are covered in section 9.

## 1. Overview

The system is one Python program that runs on the user's own computer and
shows a website in their browser. It has six parts.

```
                    ┌──────────────────────────────┐
                    │  Website (in the browser)    │
                    │  watchlist · ranking · detail│
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │  Pipeline (runs the steps)   │
                    └─┬────────┬─────────┬───────┬─┘
                      │        │         │       │
              ┌───────▼──┐ ┌───▼─────┐ ┌─▼─────┐ ┌▼─────┐
              │ Data     │ │ Signals │ │ Model │ │ Jev  │
              │ gathering│ │         │ │       │ │      │
              └───┬───┬──┘ └─────────┘ └───────┘ └──┬───┘
                  │   │                             │
     Yahoo Finance┘   └FRED                         └Claude API
                  │
              ┌───▼──────────────────────────────────────┐
              │ Storage (files on the user's computer)   │
              └──────────────────────────────────────────┘
```

| Part | What it does |
| --- | --- |
| Website | Shows the pages and takes the watchlist and time horizon from the user. |
| Pipeline | Runs the other parts in order and hands results to the website. |
| Data gathering | Downloads prices, volume, and economic data, and saves a copy. |
| Signals | Turns raw data into the numbers the model uses, such as "price change over 3 months". |
| Model | Estimates each stock's probability of rising and runs the backtest. |
| Jev | Sends the results to Claude and returns a plain-English explanation. |

## 2. Technology choices

All free. The only running cost is the Claude API credit Jev uses.

| Part | Choice | Why |
| --- | --- | --- |
| Language | Python 3.11 or newer | Decided in the product stage; the most common language for data work. |
| Website | Streamlit | Builds a web page from plain Python, with no separate HTML or JavaScript to learn. Runs locally with one command. |
| Prices, volume, market trends | `yfinance` | Free library that downloads Yahoo Finance data. No account needed. |
| Economic indicators | FRED, read with `pandas` | FRED publishes its data as plain downloadable files, so no account or key is needed. |
| Data handling | `pandas` | The standard Python tool for tables of data. |
| Model | `scikit-learn` | The standard beginner-friendly library for this kind of model. |
| Charts | Streamlit's built-in charts | Nothing extra to install. |
| Jev | `anthropic` (official Claude library) | The supported way to call Claude from Python. |
| Secrets | `python-dotenv` | Reads the `.env` file so keys never appear in code. |
| Tests | `pytest` | The standard Python testing tool. |

## 3. Data flow

1. The user starts the site with one command and opens it in the browser.
2. The site loads the saved watchlist. The user can edit it and choose a time
   horizon.
3. **Data gathering** checks storage. If today's data is already saved, it is
   reused. Otherwise it downloads price and volume history for each stock, the
   overall market (the S&P 500 index), and the economic indicators, then saves
   them.
4. **Signals** calculates the model's inputs for every stock and every past
   day.
5. **Model** learns from the past data, runs the backtest, and estimates
   today's probability of rising for each stock.
6. The pipeline sorts the stocks and picks the likely risers and likely
   fallers.
7. **Jev** is asked for an explanation of each stock. Answers are saved, so a
   stock is only sent to Claude once per day.
8. The website shows the opportunities, the ranking table, and the detail
   pages.

Steps 3 to 7 run once a day at most. Reloading the page reuses the saved
results, which keeps the site fast and the API cost low.

## 4. The probability model

### Method

Phase 1 uses **logistic regression**. It is a standard method that takes
several numbers about a stock and outputs a probability between 0% and 100%.
It was chosen because:

- it is the simplest method that produces a real probability;
- it shows how much each input pushed the probability up or down, which is
  what the stock detail page and Jev need;
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
| Market trends | S&P 500 change over the last 1 and 3 months; the stock's change compared with the S&P 500 |
| Economic indicators | Interest rate level and its recent change; inflation rate; unemployment rate; the VIX (a measure of how nervous the market is) |

### What it predicts

For each stock and day: "Will the price be higher at the end of the time
horizon than it is today?" The answer in past data is yes or no, and the model
learns the link between the inputs and that answer.

### Training data

One model is trained per time horizon, using about 10 years of daily history.
The watchlist alone is too little data to learn from, so the model also learns
from a fixed built-in list of about 50 large, well-known companies. It then
applies what it learned to the watchlist.

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

### Opportunities and confidence

Starting rules, to be tuned once real results are visible:

- **Likely riser**: probability of rising 60% or more.
- **Likely faller**: probability of rising 40% or less.
- A stock is only listed if the model beat the baseline in the backtest.
- **Confidence** is low, medium, or high, based on how far the probability is
  from 50% and how far the track record is above the baseline.

## 5. Jev

**Sent to Claude**, per stock:

- the stock's name and ticker;
- the probability of rising, the risk level, and the track record with its
  baseline;
- the input values and how much each pushed the probability up or down;
- the time horizon.

**Returned**: a short explanation with three parts: why the stock scored as it
did, what stands out, and what could make the forecast wrong.

**Keeping Jev to the page**:

- Jev's instructions tell it to use only the numbers it was sent, explain any
  term it uses, and never promise an outcome.
- Jev receives no raw price tables and has no internet access, so it cannot
  bring in outside facts.
- The same numbers Jev was sent are shown on the page, so the user can check
  every claim.

**Cost control**: answers are saved per stock per day. The Claude model name
is a setting, so a cheaper or stronger model can be chosen without changing
code.

**If Claude is unavailable**: the page still shows the probability, the
numbers, and the chart, with a note that the explanation could not be loaded.

## 6. Storage

Everything is saved as files in a `data/` folder on the user's computer. The
folder is listed in `.gitignore`, so it is never committed.

| What | File | Form |
| --- | --- | --- |
| Watchlist and time horizon | `data/watchlist.json` | Small text file |
| Price and volume history | `data/prices/<TICKER>.csv` | One table per stock |
| Economic indicators | `data/economy.csv` | One table |
| Model results and backtest | `data/results/<DATE>.json` | One file per day |
| Jev explanations | `data/jev/<DATE>.json` | One file per day |
| Daily snapshots (from phase 2) | `data/snapshots/<DATE>/` | One folder per day |

Plain files were chosen over a database because they can be opened and
inspected directly and need no setup.

## 7. Folder layout

```
src/stock_ai/
├── app.py          the website
├── pipeline.py     runs the steps in order
├── config.py       settings and loading of .env
├── storage.py      reading and writing the data/ folder
├── data/
│   ├── prices.py   Yahoo Finance downloads
│   └── economy.py  FRED downloads
├── signals.py      model inputs
├── model.py        training and probabilities
├── backtest.py     walk-forward backtest
└── jev.py          Claude call and instructions

tests/              one test file per source file, using saved sample data
                    so tests run without internet or API credit

scripts/
├── fetch_data.py   download and save data without opening the site
└── run_backtest.py run the backtest and print the track record

requirements.txt    the libraries to install
data/               local storage, not committed
```

## 8. Secrets

- The only secret in phase 1 is the Claude API key.
- It lives in `.env` as `ANTHROPIC_API_KEY=<key>`. `.env` is already in
  `.gitignore`.
- `config.py` is the only file that reads it. No other file touches the key,
  and it is never printed, logged, or sent to Jev.
- `.env.example` lists the variable names with no values, so a teammate knows
  what to fill in.
- If the key is missing, the site still runs and shows everything except the
  Jev explanations.

## 9. Later phases

Each phase adds files without reworking phase 1.

| Phase | What is added | Where it plugs in |
| --- | --- | --- |
| 2 | Company financials | New `data/financials.py`; new inputs in `signals.py` |
| 2 | News headlines for Jev | New `data/news.py`; headlines added to what Jev is sent, marked as context |
| 2 | Daily snapshots | New `data/snapshots.py`; `scripts/fetch_data.py` saves them each day |
| 3 | Options activity, short interest, institutional holdings | Shown on the detail page and sent to Jev as context; become inputs in `signals.py` once enough snapshots exist and the backtest shows they help |
| 4 | Social media | New `data/social.py`; summarized by Jev as context |

Two rules keep this clean:

- Every data source is its own file with the same shape: download, save, load.
- The model takes whatever inputs `signals.py` produces, so adding an input
  does not change the model code.

## 10. Risks and open questions

### Risks

| Risk | What it means | How it is handled |
| --- | --- | --- |
| The model may not beat the baseline | Prices are close to unpredictable, so the honest result may be "no better than guessing" | The track record and baseline are always shown; no opportunity is listed unless the baseline is beaten |
| Yahoo Finance access can break | `yfinance` is unofficial and sometimes stops working or is rate-limited | Data is saved locally, downloads happen once a day, and errors are reported plainly |
| Built-in company list flatters results | A list of companies that are large today leaves out ones that failed, which makes the past look easier to predict than it was | Stated on the track record; treated as a known limit of free data |
| Economic data arrives late | Figures such as inflation are published weeks after the month they describe | Each figure is only used from its publication date onward |
| Snapshots take time to become useful | "Latest only" data needs months of saving before it can be backtested | Saving starts in phase 2 so history is ready by phase 3 |
| API cost | Each Jev explanation uses paid credit | One call per stock per day, saved and reused |

### Decisions

Answered by the project owner on 2026-10-13. No open questions remain.

| Question | Decision |
| --- | --- |
| Website tool | Streamlit |
| Training data | About 50 large companies plus the watchlist |
| Claude model for Jev | A setting, defaulting to `claude-opus-5-5`; can be changed to a cheaper model without changing code |
| Opportunity thresholds | Likely risers at 60% or more, likely fallers at 40% or less, as starting points |
| Daily snapshots (phase 2) | Fetched manually with `scripts/fetch_data.py` to start; automation can be added later |
