# Phase 2 — Prompt

Read `00_context/project.md`, `00_context/glossary.md`, and the outputs of
`01_product` to `05_qa` first. Phase 1 is built and running.

Plan phase 2 of the Stock AI Analyzer: company financials in the model, news
headlines read by Jev, and daily saving of options activity, short interest,
and institutional holdings. Check what the free data sources really provide
before relying on them. Do not write application code.

Write the result to `06_phase2/output.md` with these sections:

1. **Where phase 1 stands** — what the first real results showed, and what
   phase 2 has to achieve.
2. **Data sources** — for each new kind of information: the free source, what
   was found when it was checked, its limits, and how much history it has.
3. **Changes to the product** — what the user sees that is new or different.
4. **Design** — new and changed files, data shapes, signals with formulas,
   storage, and how each piece avoids information from the future.
5. **Measuring whether it helps** — how to decide which new inputs stay.
6. **Risks**.
7. **Tests** — what the automated tests and manual checks add.
8. **Build order** — the steps, each ending with something that works.
9. **Open questions** — decisions that need a human answer.

Rules:

- Prefer the simplest approach that is correct.
- Explain any technical term a beginner might not know.
- Stay consistent with the names and decisions in the earlier stages. If a
  change to an earlier decision is needed, say so and say why.
