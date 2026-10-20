# Data — Prompt

Read `00_context/project.md`, `00_context/glossary.md`,
`01_product/output.md`, `02_architecture/output.md`, and `03_api/output.md`
first.

Define exactly what data phase 1 of the Stock AI Analyzer collects, how it is
cleaned and stored, and how it becomes the model's inputs. Do not write
application code.

Write the result to `04_data/output.md` with these sections:

1. **Datasets** — for each dataset (S&P 500 list, price history, latest
   prices, splits, economic indicators): the source, exactly what is
   requested, how often it is updated, and roughly how large it is.
2. **Time rules** — which calendar the data follows, how dates and times are
   recorded, and how the data is kept free of information from the future,
   including the publication delay of economic figures.
3. **Cleaning and checks** — the problems each dataset can have and what is
   done about each one.
4. **Signals** — the exact formula for every model input and for the outcome
   the model learns to predict, in plain words and as a formula.
5. **Model and backtest data** — which rows are used to train, which to test,
   and how the walk-forward periods are laid out so the test never sees
   training information.
6. **Stored files** — every file in `data/`, with its columns or fields,
   units, and when it is written.
7. **Test data** — the small sample data the tests use instead of downloads.
8. **Open questions** — decisions that need a human answer.

Rules:

- Prefer the simplest approach that is correct.
- Explain any technical term a beginner might not know.
- Stay consistent with the names and decisions in the earlier stages. If a
  change to an earlier stage is needed, say so and say why.
