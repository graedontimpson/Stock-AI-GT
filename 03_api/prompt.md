# API — Prompt

Read `00_context/project.md`, `00_context/glossary.md`,
`01_product/output.md`, and `02_architecture/output.md` first.

Define the interfaces for phase 1 of the Stock AI Analyzer: how the parts of
the program talk to each other and to outside services. An interface is the
agreed shape of a request and its answer. Do not write application code.

Write the result to `03_api/output.md` with these sections:

1. **Internal interfaces** — for each file in the architecture's folder
   layout, the functions other files may call: name, inputs, what it returns,
   and what happens on failure.
2. **Shared data shapes** — the tables and records passed between parts
   (price history, signals, a stock's result, a Jev explanation), with each
   field named and described.
3. **Outside services** — for Yahoo Finance, FRED, and the Claude API: what
   is requested, what comes back, known limits, and how failures are handled.
4. **Jev's contract** — exactly what Jev is sent and the structure of what it
   must return, with one worked example.
5. **Errors** — the list of things that can go wrong and the plain-language
   message the user sees for each.
6. **Settings** — every setting and `.env` variable, with its default.
7. **Open questions** — decisions that need a human answer.

Rules:

- Prefer the simplest interface that works.
- Explain any technical term a beginner might not know.
- Stay consistent with the names and decisions in `02_architecture/output.md`.
