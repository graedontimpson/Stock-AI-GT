# QA — Prompt

Read `00_context/project.md`, `00_context/glossary.md`, and the outputs of
`01_product` to `04_data` first.

Define how phase 1 of the Stock AI Analyzer is checked, so the team knows it
works before it is used. QA means quality assurance: making sure the product
does what it should. Do not write test code.

Write the result to `05_qa/output.md` with these sections:

1. **Approach** — the kinds of checks used and what each is for.
2. **Automated tests** — for each source file, the specific cases to test,
   including the error cases from the API stage.
3. **Correctness checks for the model** — how to confirm there is no
   look-ahead, that the backtest is honest, and that the model behaves
   sensibly on data where the right answer is known.
4. **Account checks** — the rules that must always hold for the paper trading
   account, and how they are tested.
5. **Outside services** — how Yahoo Finance, FRED, Wikipedia, and Claude are
   checked without depending on them in everyday tests.
6. **Secrets** — how to confirm no credentials reach the code or a commit.
7. **Manual checklist** — what a person clicks through on the site before
   phase 1 is called done.
8. **Definition of done** — the conditions phase 1 must meet.
9. **Open questions** — decisions that need a human answer.

Rules:

- Prefer the simplest checks that would catch real problems.
- Explain any technical term a beginner might not know.
- Stay consistent with the names and decisions in the earlier stages.
