# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Layout

- `00_context/` — shared background. Read `project.md` and `glossary.md` before any stage.
- `01_product/` to `05_qa/` — one folder per stage, run in order. Each holds:
  - `prompt.md` — the instructions for that stage.
  - `output.md` — the result of running that prompt.
- `src/` — application code.
- `tests/` — tests.
- `scripts/` — helper and one-off scripts.

## Rules

- Each stage builds on the `output.md` of the stages before it; read them first.
- Write a stage's result to its own `output.md`; do not edit another stage's output.
- Use terms as defined in `00_context/glossary.md`.
- Secrets live in `.env` (gitignored). Keep `.env.example` in sync with the variable names, without values.
