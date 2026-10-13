# Architecture — Prompt

Read `00_context/project.md`, `00_context/glossary.md`, and
`01_product/output.md` first.

Design how the Stock AI Analyzer is put together. Cover all four phases at a
high level and phase 1 in detail. Do not write application code.

Write the result to `02_architecture/output.md` with these sections:

1. **Overview** — the main parts of the system and what each one does, with a
   simple diagram.
2. **Technology choices** — the language, libraries, and tools for each part,
   with a one-line reason for each. Free options only.
3. **Data flow** — what happens, step by step, from the user opening the site
   to the page being shown.
4. **The probability model** — the method used in phase 1, why it was chosen,
   and how the backtest works, explained for a beginner.
5. **Jev** — what Jev is sent, what it returns, and how it is kept to the
   information on the page.
6. **Storage** — what is saved on the user's computer (watchlist, fetched
   data, daily snapshots) and in what form.
7. **Folder layout** — how `src/`, `tests/`, and `scripts/` are organized.
8. **Secrets** — how API keys are loaded from `.env` and kept out of code and
   commits.
9. **Later phases** — where phases 2 to 4 plug in without reworking phase 1.
10. **Risks and open questions** — what could go wrong and what needs a human
    decision.

Rules:

- Prefer the simplest design that works.
- Explain any technical term a beginner might not know.
- Every choice must respect the decisions in `01_product/output.md`.
