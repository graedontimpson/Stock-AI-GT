# Stock AI — Team 07

A personal paper trading website. Trade S&P 500 stocks with pretend money at
real prices, and get an AI Buy / Hold / Sell suggestion for each stock, with a
plain-English explanation from Jev and an honest track record.

Suggestions are estimates from past prices, not guarantees. All money on the
site is pretend.

## Setup

You need Python 3.11 or newer (3.14 is used for development). Check with
`python3 --version`.

From the project folder, in Terminal:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
cp .env.example .env
```

Then open `.env` and put your Claude API key after `ANTHROPIC_API_KEY=`, with
no quotes, spaces, or brackets. Without a key the site still works; it just
shows no Jev explanations.

## Running the site

```
.venv/bin/streamlit run src/stock_ai/app.py
```

Your browser opens the site. **The first run downloads 10 years of prices for
about 500 stocks and runs the backtest, which takes several minutes.** After
that, the site updates once a day, the first time you open it.

You can also run the daily update from Terminal without opening the site:

```
.venv/bin/python scripts/daily_update.py
```

Everything the site saves (prices, your account, results) is in the `data/`
folder, which is never committed. To back up your account, copy
`data/account/` somewhere safe.

## Tests

```
.venv/bin/pytest
```

The tests use made-up data in `tests/fixtures/`, so they need no internet and
no API credit. GitHub also runs them on every push.

To check that the outside services (Wikipedia, Yahoo Finance, FRED) still
answer as expected:

```
.venv/bin/python scripts/smoke_check.py           # free
.venv/bin/python scripts/smoke_check.py --claude  # also checks the API key; uses a tiny amount of credit
```

## Workspace map

```
├── CLAUDE.md       README.md       .gitignore
├── .env.example    requirements.txt    pyproject.toml
├── 00_context/     project.md + glossary.md
├── 01_product/     prompt.md + output.md
├── 02_architecture/ prompt.md + output.md
├── 03_api/         prompt.md + output.md
├── 04_data/        prompt.md + output.md
├── 05_qa/          prompt.md + output.md
├── src/stock_ai/   the application
├── tests/          automated tests and fixtures
└── scripts/        daily update, backtest, smoke check, fixtures
```

The design is in the numbered folders; read `00_context/project.md` first.
