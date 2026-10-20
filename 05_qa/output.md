# QA — Output

How phase 1 of the Stock AI Analyzer is checked before it is used.

## 1. Approach

Four kinds of checks, from fastest to slowest:

| Kind | What it is | When it runs |
| --- | --- | --- |
| **Automated tests** | Small programs that run a piece of the code with known inputs and check the result. Run with `pytest`. They use the made-up data in `tests/fixtures/`, so they need no internet and no API credit. | Before every commit |
| **Model correctness checks** | Automated tests on specially built data where the right answer is known, to catch mistakes that make a model look better than it is. | Before every commit |
| **Smoke checks** | A quick test against the real outside services, to see that they still answer in the expected shape. The name comes from switching on a machine and checking nothing smokes. | Once before building starts, then when something breaks |
| **Manual checklist** | A person clicks through the site and checks it by eye. | Before phase 1 is called done, and after any big change |

All automated tests are run with one command:

```
pytest
```

## 2. Automated tests

Each test file matches a source file. "Raises X" means the test checks that
the named error from the API stage happens.

### `config.py`

- Loads settings with their defaults when `.env` has nothing in it.
- Reads `ANTHROPIC_API_KEY` and `JEV_MODEL` when set.
- Records a missing key as "not set" without failing.

### `storage.py`

- Every save followed by a load gives back the same data.
- Loading a file that does not exist returns nothing, without failing.
- `append_trade` adds a row and never changes earlier rows.
- `archive_account` copies both account files into the archive folder.

### `data/universe.py`

- Converts `BRK.B` to `BRK-B`.
- Removes duplicate tickers.
- A list of under 490 or over 510 tickers is rejected and the saved list is
  used, marked out of date.
- `is_in_sp500` is right for a listed and an unlisted ticker.

### `data/prices.py`

Using fixture data in place of downloads:

- Days with no close are removed.
- A zero or negative price causes the ticker to be skipped.
- Duplicate dates keep the last one.
- A gap of up to 5 days is filled with the previous prices, zero volume, and
  `filled` set to yes; a longer gap causes the ticker to be skipped.
- When the overlapping days differ by more than 0.01%, the full history is
  downloaded again; when they match, only new rows are added.
- `get_latest_price` raises `PriceUnavailableError` for no price, a zero
  price, or a price over 4 days old while the market has been open.
- `get_latest_price` never returns a saved price as a fallback.

### `data/economy.py`

- FRED's missing-value dots are removed and the previous value carries
  forward.
- A failed download returns the saved copy, marked out of date.

### `signals.py`

- Each of the 15 signals matches a value worked out by hand for one fixture
  day.
- `inflation` uses the CPI from 12 months earlier.
- Monthly figures appear only from the first trading day of the second month
  after (the September figure first appears in November).
- `interest_rate` uses the previous day's `DFF`.
- No row is created for a day missing any signal.
- Raises `NotEnoughHistoryError` for under 1 year of prices.
- `rose` is yes when the price 63 trading days later is higher, no
  otherwise, and empty for the last 63 days.

### `model.py`

- Predictions are between 0 and 1.
- The contributions add up to the difference between the prediction and the
  model's starting point, so the stock page's explanation of "what pushed it
  up or down" is complete.
- Standardization is worked out from training rows only.
- Raises `NotEnoughHistoryError` with too few rows.

### `backtest.py`

- The first training period is 3 years; test periods are 6 months.
- Every step leaves a 63-trading-day gap between training and testing.
- No test row's date is ever inside its own training data.
- The baseline is the share of test rows where the price rose.

### `suggestions.py`

- 0.60 gives Buy, 0.59 gives Hold, 0.40 gives Sell, 0.41 gives Hold.
- A stock that does not beat its baseline is always Hold, whatever its
  probability.
- Each confidence level matches the rule in the API stage at its edges.
- Risk is low, medium, or high by volatility third.
- `top_picks` returns at most 10 of each, in the right order, and empty
  lists when nothing qualifies.

### `pipeline.py`

- A full daily run on the fixtures produces results for every good ticker
  and lists the bad ones in `skipped` with a reason.
- A second run on the same day returns the saved results without
  recalculating.
- Missing SPY data raises `DataUnavailableError`.
- `get_suggestion` raises `NotInSP500Error` for an unlisted ticker.
- `get_explanation` calls Jev only once per stock per day.

### `account.py`

See section 4.

### `scorecard.py`

- Saves each Buy and Sell suggestion once per stock per day; Holds are not
  saved.
- `mark_due` marks a Buy right when the adjusted close rose and a Sell right
  when it fell.
- Suggestions not yet due are left alone.
- A due suggestion with no price available is left for the next day.
- The scorecard's counts and averages match a hand-worked example.

### `jev.py`

Claude is replaced by a stand-in that returns prepared answers, so no real
request is ever made in tests.

- A correct answer is returned with status `ok`.
- An answer missing a field, or with extra fields, gives status
  `unavailable`.
- A failed request is retried once, then gives `unavailable`.
- No key gives `unavailable` with the "no API key" message, without trying a
  request.
- The request contains exactly the `Suggestion` fields and `shares_owned`,
  and never the API key.

### Error messages

- Every error in the API stage's error table produces its exact message,
  with the placeholders (ticker, amounts, dates) filled in.

## 3. Correctness checks for the model

These catch the mistakes that make a stock model look good when it is not.

### No look-ahead

- **Future-change test**: build signals from the fixtures, then change every
  price after a chosen day to random numbers and build them again. Every
  signal up to and including that day must be identical. If any changed, a
  signal is using future data.
- **Monthly figure test**: change the CPI for a month and check that no
  signal changes before the first trading day of the second month after.

### Honest backtest

- **Random data test**: make up price histories that move completely at
  random. The model's track record must come out close to the baseline
  (within 2 points). If it is clearly better, the backtest is leaking
  information.
- **Gap test**: remove the 63-day gap and confirm the random data test now
  scores higher. This proves the gap is doing its job.

### Sensible behavior

- **Planted pattern test**: make up data where one signal really does
  predict the outcome, for example stocks above their 200-day average rise
  70% of the time. The model must beat the baseline, and that signal must
  have the largest contribution.
- **Probability check**: across the fixture backtest, stocks given about 70%
  should rise about 70% of the time, within a reasonable margin. This is
  called **calibration**: a probability should mean what it says.

## 4. Account checks

### Rules that must always hold

Checked after every step of every account test:

- Cash is never below zero.
- Shares owned of any stock are never below zero.
- Cash equals the starting cash, minus every buy's cost, plus every sell's
  proceeds.
- Shares owned equal all buys, minus all sells, plus all split shares.
- The portfolio's total value equals cash plus the value of all holdings.
- The trade list only ever grows; no row is ever changed or removed.

### Cases

| Case | Expected |
| --- | --- |
| Buy with enough cash | Trade recorded; cash goes down by shares × price |
| Buy costing exactly all the cash | Allowed; cash becomes $0 |
| Buy costing $0.01 more than the cash | `NotEnoughCashError`; nothing recorded |
| Buy 0, −1, or 1.5 shares | `InvalidSharesError`; nothing recorded |
| Buy a ticker not in the S&P 500 | `NotInSP500Error`; nothing recorded |
| Buy when no price is available | `PriceUnavailableError`; nothing recorded |
| Sell some of a holding | Trade recorded; cash goes up; average cost unchanged |
| Sell all of a holding | Holding disappears from the portfolio |
| Sell more than owned, or a stock not owned | `NotEnoughSharesError`; nothing recorded |
| Sell a stock that has left the S&P 500 | Allowed |
| Buy the same stock twice at different prices | Average cost is the weighted average |
| A 2-for-1 split | Shares double, average cost halves, value and gain unchanged |
| The same split seen on two daily updates | Applied only once |
| Reset | Old files archived; new account with $100,000 and no trades |
| Performance right after opening | Account and SPY comparison both show 0% |
| Trade records the suggestion | `suggestion_at_time` matches that day's suggestion |

## 5. Outside services

Everyday tests never contact outside services. Instead:

- **Stand-ins**: tests replace Yahoo Finance, FRED, Wikipedia, and Claude
  with stand-ins that return fixture data or prepared answers, including
  failures, so every error path is tested.
- **Smoke check script**: `scripts/smoke_check.py` contacts each real
  service once and reports whether it answered in the expected shape:
  - Wikipedia: the S&P 500 table exists, with between 490 and 510 rows and
    the expected columns.
  - Yahoo Finance: 1 month of history for `AAPL` and `SPY` with the expected
    columns; a latest price for `AAPL`; split records for a stock known to
    have split.
  - FRED: each of the four series downloads, with dates and numbers.
  - Claude: one small request with the real key returns a correctly shaped
    Jev answer. This uses a tiny amount of API credit, so it only runs when
    asked.
- The smoke check runs once before building starts, to confirm the details
  in `04_data/output.md`, and again whenever a download starts failing.

## 6. Secrets

- An automated test searches every file that git tracks for text shaped
  like an Anthropic key (starting `sk-ant-`) or a GitHub token (starting
  `ghp_` or `github_pat_`), followed by at least 20 more letters, digits,
  dashes, or underscores, and fails if it finds one. The length rule stops
  the prefixes written in this document from counting as keys.
- An automated test confirms `.env` is listed in `.gitignore` and
  `.env.example` contains no values.
- The `jev.py` tests confirm the key is never part of a request.
- Before each push, `git status` is checked to confirm `.env` and `data/`
  are not being committed.

## 7. Manual checklist

Done on a fresh copy of the project, with an empty `data/` folder.

**Setup**

- [ ] Following the README from scratch gets the site running.
- [ ] The first run shows a progress message and finishes within 15
      minutes.
- [ ] The site starts without an API key and shows the "no API key" note
      where Jev's explanation would be.

**Home page**

- [ ] Shows $100,000 cash and 0% performance on a new account.
- [ ] Shows up to 10 top Buys and Sells, or "nothing stands out".

**Stock page**

- [ ] Search finds a stock by ticker.
- [ ] The chart, suggestion, probability, confidence, risk, track record, and
      baseline are shown.
- [ ] With a key set, Jev's explanation appears, uses only numbers shown on
      the page, and contains no promises.
- [ ] Opening the same stock again the same day does not make a new Claude
      request.
- [ ] The price's time is shown.

**Trading**

- [ ] Buying updates cash, the portfolio, and the trade history.
- [ ] Each error from section 4 shows its plain-language message.
- [ ] Selling part and then all of a holding works.
- [ ] Reset asks for confirmation, archives the old account, and starts
      fresh.

**Portfolio and scorecard**

- [ ] Gains and losses match a hand calculation for one holding.
- [ ] Performance against SPY is shown.
- [ ] The scorecard shows the backtest result and when the first real
      results are due.

**Next day**

- [ ] Opening the site the next day runs the daily update once and shows
      new suggestions.

## 8. Definition of done

Phase 1 is done when all of these are true:

1. Every automated test passes, locally and in the automatic GitHub run.
2. The smoke check passes for Wikipedia, Yahoo Finance, FRED, and Claude.
3. The manual checklist is complete.
4. The backtest has run on the real data, and its track record and baseline
   are shown on the site, whatever they turn out to be. Beating the baseline
   is not required for phase 1 to be done; showing the honest result is.
5. The secrets checks pass, and a one-time scan of the whole git history
   finds no credentials.
6. The README explains setup, the first run, and how to run the tests.
7. The team has reviewed and approved it.

## 9. Decisions

| Question | Decision | Date |
| --- | --- | --- |
| Automatic test runs on GitHub | Set up in phase 1: `pytest` runs on every push, free | 2026-10-20 |
| Scan of the whole git history for credentials | Added to the definition of done as a one-time check | 2026-10-20 |

No open questions remain.
