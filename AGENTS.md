# AGENTS.md

Guidance for AI agents working in this repo (Claude Code, Codex CLI, Cursor, Gemini CLI, ...). Chat-only tools: see [Chat-only tools](#chat-only-tools).

## Load skills before the work they cover

Skills live in `./skills/`. They are canonical; this file only routes to them.

- Read the referenced skill file in full before starting that kind of work.
- This file's standards override a skill where they conflict.
- Never claim a skill was applied unless you read its file. Name the skills you loaded in your completion message.

## Python standards (source of truth)

`pyproject.toml` is authoritative: Python >= 3.10, ruff line-length 100, lint rules E,F,I,W, pytest from `tests/`.

- Type hints on public functions.
- Imports sorted and grouped as ruff `I` enforces; no unused imports.
- Explicit exceptions; no bare `except`, no silent `pass` on error paths.
- Pandera schemas in `src/bubi/contracts/schemas.py` and the 7-table data contract are frozen. Never relax, rename, or widen them just to get a check passing.
- Functions return data; the dashboard/CLI layer does I/O and printing.
- Keep comments that explain *why*. Delete comments that restate the code.

## Commands

`make install`, `make test`, `make lint`, `make format`, `make fixtures`, `make dashboard`.

CI (`.github/workflows/ci.yml`) runs `ruff check`, `ruff format --check`, `python scripts/generate_fixtures.py`, `pytest tests/ -v`. Cite only commands that exist in the `Makefile` or CI.

## Skill routing

| Skill | Load when | Do not load |
|---|---|---|
| `./skills/technical-writing.md` | Writing or editing technical documentation or human-facing prose: `README.md`, `docs/*.md`, `bubi-technical-design.md`, `src/bubi/*/README.md`, API references, user guides, tutorials, changelogs, architecture docs, explanatory PR or issue text | Code comments, commit messages, `AGENTS.md`/`CLAUDE.md`, changelog bullet stubs |
| `./skills/code-simplifier.md` | Second pass only: after implementation is written and `make test` + `make lint` pass | During first implementation; tests, fixtures, `scripts/generate_fixtures.py`, configs, data, notebooks, `.venv`, generated files |

## Code work: two passes

1. Implement the change without `code-simplifier`.
2. Get green: `make test` and `make lint` pass.
3. Read `./skills/code-simplifier.md` in full, then simplify only files touched in this session.
4. Behavior is frozen: signatures, public names, outputs, Pandera schemas. Re-run both commands; revert the simplification if either fails.
5. Cannot switch to a strong coding model with high reasoning? Ask the user instead of proceeding at low effort.
6. Do not simplify code you did not touch unless explicitly asked.

## Docs work

- Load `technical-writing` first and follow its workflow: identify document type and audience, gather source material, design structure, write, cross-reference, verify.
- Every command, path, and code sample must run against this repo. Verify before publishing; if you cannot verify, say so.
- Default audience: teammates and BKK-facing reviewers — Python-literate, not OSM/network experts. Define domain acronyms on first use.
- No TODO or placeholder text. List missing source material instead of inventing it.

## Before you say done

- Skills loaded (or "none") and why.
- Commands run and their actual result, not "tests should pass".
- Files touched, and whether the change preserves behavior.
- Anything unverified, labelled as unverified.

## Chat-only tools

Claude Chat cannot run `make` targets. A repo snapshot in Project knowledge is a snapshot, not a live checkout. Its simplification output is a proposed patch that a human or CLI agent applies and verifies. Never describe chat output as verified.

## Skills are read-only

Do not edit `./skills/*.md` as part of normal work. If a skill looks wrong for this repo, report it — do not patch it in the same change.
