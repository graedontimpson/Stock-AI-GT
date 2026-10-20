# Stock AI Analyzer

## Goal

Build a beginner-friendly paper trading website: the user trades S&P 500
stocks with fake money at real prices, and an AI suggests whether to buy,
sell, or hold each stock, with a reason.

## Later

Built in phases; see `01_product/output.md` for the full definition.

- Yahoo data and other free data sources
- A paper trading account: cash, holdings, trades, and performance
- Useful calculations and a probability model with a backtested track record
- Jev analysis: Buy, Sell, or Hold suggestions explained in plain English
- A result the user can read

## Current stage

Design. The product, architecture, and API stages were revised on 2026-10-20
for paper trading. The data and QA stages are done, so planning is
complete. Building phase 1 is next, once the team approves it.

## Rules

- Keep credentials out of source code and commits.
- Prefer simple solutions.
- Explain unfamiliar concepts.
- Wait for human approval before implementing features.
- Use free data sources only.
- Paper trading only: the site never connects to a real brokerage or real money.
