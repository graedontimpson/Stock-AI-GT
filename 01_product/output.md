# Product — Output

Product definition for the Stock AI Analyzer: a personal paper trading
website. The user trades S&P 500 stocks with fake money at real prices, and
the AI suggests whether to buy, sell, or hold each stock.

Revised on 2026-10-20. The previous version (a forecasting site without
trading) is in the git history.

## 1. User

One person, using the site for themselves. They are a beginner: they know what
a stock is and want to learn how trading works and whether AI suggestions help,
without risking real money. The site is not shared with the public.

## 2. Problem

The user wants to practice trading and answer two questions:

- "Should I buy, sell, or hold this stock right now?"
- "If I had followed the AI's suggestions, would I have made money, and would I
  have done better than simply buying the whole S&P 500?"

## 3. What paper trading is

**Paper trading** means trading with pretend money. Prices are real, but no
real money changes hands. It is how people practice and test ideas safely.

## 4. What a prediction can and cannot do

- Nobody can reliably predict stock prices. Professional funds with far more
  data mostly fail to beat the market average over time.
- The AI's suggestions are estimates from past data, so they will often be
  wrong.
- The site therefore keeps score: every suggestion is recorded and checked
  later against what really happened. Paper trading is the ideal place to find
  out whether the suggestions are worth anything.

## 5. Features

### Paper trading account

- Starts with **$100,000** of pretend cash. The user can reset it at any time.
- **Buy** any S&P 500 stock in whole shares, if there is enough cash.
- **Sell** shares the user owns. Selling shares you do not own (called
  **short selling**) is not allowed.
- Trades happen immediately at the latest price from Yahoo Finance. During
  market hours this price may be about 15 minutes old; outside market hours it
  is the last closing price. No trading fees.
- **Portfolio page**: cash, each stock owned, what was paid, what it is worth
  now, and the gain or loss.
- **Trade history**: every trade with date, stock, shares, and price.
- **Performance**: the account's total gain or loss compared with what the
  same starting cash would have made in an S&P 500 index fund over the same
  period. This shows whether the user is beating the simplest alternative.

### AI suggestions

- For any S&P 500 stock the user looks at, the AI gives:
  - **Buy**, **Hold**, or **Sell**;
  - the **probability** that the price will be higher in 3 months, for
    example "64% likely to rise";
  - a **confidence level** (low, medium, or high);
  - the **track record**: how often this method was right in past data,
    compared with always guessing "rise";
  - a plain-English **reason from Jev**, including what could make the
    suggestion wrong.
- **Buy** means the AI expects the price to rise. **Sell** means it expects
  the price to fall; for a stock the user does not own, it reads as "avoid for
  now". **Hold** means the AI has no strong view.
- Suggestions are only advice. The user always clicks to place a trade; the AI
  never trades on its own.

### Daily picks

- Each day the AI scores all S&P 500 stocks and shows the **top Buy
  suggestions** and **top Sell suggestions**.
- Stocks the user owns are always shown with their current suggestion.
- Some days the honest answer is "nothing stands out".

### Suggestion scorecard

- Every suggestion shown is recorded with its date and price.
- Once 3 months have passed, it is marked right or wrong.
- The scorecard shows how many suggestions were right, and how a pretend
  account that followed every suggestion would have done compared with the
  S&P 500.

## 6. Information the predictions use

Unchanged from the previous version. The goal is to use twelve kinds of
information, added in phases:

| Information | Free source | Past values available |
| --- | --- | --- |
| Historical prices | Yahoo Finance | Yes |
| Trading volume | Yahoo Finance | Yes |
| Market trends | Yahoo Finance (index prices) | Yes |
| Economic indicators | FRED (US central bank data service) | Yes |
| Company financials | Yahoo Finance | A few years |
| News | Yahoo Finance, news services | Recent only |
| World events | Picked up through news | Recent only |
| Investor sentiment and behavior | Market "fear index" (VIX); tone of news | Partly |
| Options activity | Yahoo Finance | Today's only |
| Short interest | Yahoo Finance | Latest only |
| Institutional buying and selling | Yahoo Finance (quarterly filings) | Latest only |
| Social media | Limited free access | Recent only |

Information with years of history goes into the **probability model**, where
its accuracy can be backtested. Information without history is read by **Jev
as context**: Jev says whether it supports or contradicts the suggestion, but
it does not change the number. The site saves a copy of "latest only"
information each day so it can join the model later.

## 7. User flow

1. The user opens the site on their own computer.
2. The home page shows the account value, performance against the S&P 500,
   the stocks owned with their suggestions, and today's top Buy and Sell picks.
3. The user searches for a stock or clicks one.
4. The stock page shows the price chart, the Buy/Hold/Sell suggestion, the
   probability, confidence, track record, and Jev's reason.
5. The user enters a number of shares and clicks Buy or Sell, or does nothing.
6. The portfolio and trade history update.

If something goes wrong (unknown ticker, no internet, not enough cash), the
site says what happened in plain language and what to try next.

## 8. Phases

Each phase ends with a working site.

**Phase 1 — trading and core predictions**

- Paper trading account: buy, sell, portfolio, trade history, performance
  against the S&P 500, reset.
- Price data for all S&P 500 stocks.
- Model built on historical prices, trading volume, market trends, and
  economic indicators.
- Buy/Hold/Sell suggestion, probability, confidence, and track record per
  stock.
- Daily top picks and Jev explanations.
- Suggestion scorecard starts recording.

**Phase 2 — company and news context**

- Company financials added to the model.
- News headlines read by Jev, covering world events and investor sentiment.
- Daily saving of options activity, short interest, and institutional
  holdings begins.

**Phase 3 — market positioning**

- Options activity, short interest, and institutional buying and selling
  shown on the stock page and used by Jev as context.
- Each is moved into the model once enough saved history exists and the
  backtest shows it helps.

**Phase 4 — social media**

- Social media discussion summarized by Jev, using free access only.

## 9. Out of scope

- Real money, or connecting to a real brokerage.
- Connecting to an outside paper trading service such as Alpaca.
- Stocks outside the S&P 500, funds other than the S&P 500 comparison, and
  other assets such as crypto or options.
- Short selling, fractional shares, and order types other than "trade now"
  (such as limit or stop orders).
- The AI placing trades by itself.
- Live, second-by-second prices.
- Publishing the site on the internet, logins, or multiple users.
- Paid data sources.

## 10. Decisions

| Question | Decision | Date |
| --- | --- | --- |
| Build in phases or all at once | Phases, as in section 8 | 2026-10-13 |
| Paid data | Free sources only | 2026-10-13 |
| Where the site runs | On the user's own computer only | 2026-10-13 |
| Programming language | Python | 2026-10-13 |
| AI provider for Jev | Anthropic's Claude | 2026-10-13 |
| Where the paper account lives | Built into the site, not an outside service | 2026-10-20 |
| Which stocks | Any S&P 500 stock | 2026-10-20 |
| Who places trades | The user; the AI only suggests | 2026-10-20 |
| Starting cash | $100,000 | 2026-10-20 |
| Suggestion horizon | 3 months | 2026-10-20 |
| Buy and Sell thresholds | Buy at 60% or higher chance of rising, Sell at 40% or lower, Hold in between, as starting values | 2026-10-20 |
| Team alignment on the move to paper trading | Agreed by the team | 2026-10-20 |

No open questions remain.
