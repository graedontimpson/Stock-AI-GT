# Product — Output

Product definition for the Stock AI Analyzer: a personal website that
estimates the probability of each stock on a watchlist rising or falling,
using many kinds of market information, and points out the most promising
opportunities.

## 1. User

One person, using the site for themselves. They are a beginner: they know what
a stock is and can find a ticker symbol, but terms like "short interest" or
"moving average" are new to them. The site is not shared with the public.

## 2. Problem

The user wants to answer: "Out of the stocks I'm watching, which are most
likely to rise, which are most likely to fall, and where is the best
opportunity?" They want a clear answer with reasons they can understand.

## 3. What a forecast can and cannot do

- Nobody can reliably predict stock prices. Professional funds with far more
  data mostly fail to beat the market average over time.
- Adding more kinds of information does not automatically make a forecast
  better. Each one has to earn its place by improving the track record.
- So every probability on the site comes with a **track record**: how often
  the same method was right when run on past data. This check is called a
  **backtest**. It is how the user decides how much to trust the site.

## 4. Input

- **Watchlist** — the ticker symbols the user wants compared, for example
  `AAPL`, `MSFT`, `VOO`. A ticker symbol is the short code a stock trades
  under. Up to 10 in the first phase.
- **Time horizon** — how far ahead to forecast: 1 month, 3 months, or 6 months.
  The default is 3 months.

## 5. Information the forecast uses

The goal is to use all twelve kinds of information below. They differ a lot in
how easy they are to get and whether past values are available. Past values
matter because without them a signal cannot be backtested.

| Information | What it is | Free source | Past values available |
| --- | --- | --- | --- |
| Historical prices | Daily prices going back years | Yahoo Finance | Yes |
| Trading volume | How many shares change hands each day | Yahoo Finance | Yes |
| Market trends | How the overall market and the stock's industry are moving | Yahoo Finance (index prices) | Yes |
| Economic indicators | Interest rates, inflation, unemployment | FRED (US central bank data service) | Yes |
| Company financials | Revenue, profit, debt, reported each quarter | Yahoo Finance | A few years |
| News | Headlines about the company | Yahoo Finance, news services | Recent only |
| World events | Wars, elections, policy changes | No direct feed; picked up through news | Recent only |
| Investor sentiment and behavior | Whether investors are fearful or optimistic | Market "fear index" (VIX); tone of news | Partly |
| Options activity | Bets on a stock rising (calls) or falling (puts) | Yahoo Finance | Today's only |
| Short interest | Shares borrowed to bet on a fall | Yahoo Finance | Latest only, updated twice a month |
| Institutional buying and selling | What large funds hold | Yahoo Finance (quarterly filings) | Latest only, weeks out of date |
| Social media | What people are saying on Reddit, X, and similar | Limited; full access is paid | Recent only |

Because of this, the information is used in two ways:

- **In the probability model** — information with years of past values. The
  model learns from history how these related to later price moves, and its
  accuracy can be backtested.
- **As context from Jev** — information with no usable history yet. Jev reads
  it and explains whether it supports or contradicts the model's probability.
  It does not change the number, because its effect cannot be checked.

The site saves a copy of the "latest only" information each day. Once enough
has built up, it can be backtested and moved into the model.

## 6. Output

One page with four parts:

1. **Opportunities** — the stocks that stand out, in two lists: **likely
   risers** and **likely fallers**. The fallers list works as a warning for
   stocks the user already owns. Each entry has a short plain-English reason
   and a confidence level (low, medium, or high). A stock only appears when
   its probability is strong and the track record supports it. Some days the
   honest answer is "nothing stands out".
2. **Ranking table** — every stock on the watchlist, showing:
   - **Probability of rising** — the model's estimate that the price will be
     higher at the end of the time horizon, for example "62% likely to rise".
     50% means a coin flip.
   - **Risk** — how bumpy the price has been, based on volatility (how much
     the price swings from day to day).
   - **Track record** — how often the model got the direction right for this
     stock in the backtest.
3. **Stock detail** — click a stock to see a price chart, which pieces of
   information pushed the probability up or down, and the Jev analysis.
4. **Jev analysis** — the AI-written part. Jev receives the model's
   probability, the numbers behind it, and the context information (news,
   options activity, short interest, and so on). It explains in plain English
   why the stock scored as it did, what the context adds, and what could make
   the forecast wrong. It only refers to information shown on the page.

Each page carries one line stating that probabilities are estimates from past
data, not guarantees.

## 7. User flow

1. The user opens the site on their own computer.
2. They enter or edit their watchlist and pick a time horizon.
3. The site gathers the information for each stock.
4. The model calculates each stock's probability of rising and its track
   record.
5. Jev reads the results and the context information and writes the
   explanations.
6. The user reads the opportunities, then clicks into any stock for detail.

If something goes wrong (unknown ticker, no internet, a source unavailable),
the site says what happened in plain language and carries on with the
information it does have.

## 8. Phases

Building all twelve at once would make it impossible to tell which ones help.
Each phase ends with a working site.

**Phase 1 — core model**

- Website running on the user's own computer, with a saved watchlist.
- Model built on historical prices, trading volume, market trends, and
  economic indicators.
- Probability of rising, risk, and backtested track record per stock.
- Opportunities list, ranking table, and stock detail with a price chart.
- Jev explanation of each result.

**Phase 2 — company and news context**

- Company financials added to the model.
- News headlines read by Jev, covering world events and the tone of coverage
  (investor sentiment).
- Daily saving of options activity, short interest, and institutional
  holdings begins.

**Phase 3 — market positioning**

- Options activity, short interest, and institutional buying and selling
  shown on the stock detail page and used by Jev as context.
- Each is moved into the model once enough saved history exists and the
  backtest shows it helps.

**Phase 4 — social media**

- Social media discussion summarized by Jev, using free access only.
- Left to last because free access is limited and the signal is the noisiest.

## 9. Out of scope

- Scanning the whole market for picks; the site ranks the watchlist only.
- Buying or selling stocks, or connecting to a brokerage account.
- Deciding how much money to invest or how to split it.
- Live or minute-by-minute prices.
- Publishing the site on the internet, logins, or multiple users.
- Paid data sources.

## 10. Decisions

Answered by the project owner on 2026-10-13. No open questions remain.

| Question | Decision |
| --- | --- |
| Build in phases or all at once | Phases, as in section 8 |
| Paid data | Free sources only |
| Risers, fallers, or both | Show both |
| Where the site runs | On the user's own computer only |
| Programming language | Python |
| AI provider for Jev | Anthropic's Claude; each explanation uses a small amount of paid API credit |
| Team alignment on the move from "analyzer" to forecasting | Agreed by the team; `00_context/project.md` updated to match |
