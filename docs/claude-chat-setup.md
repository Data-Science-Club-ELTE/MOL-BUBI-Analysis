# Using Claude Chat on MOL Bubi (Free plan)

Setup and daily use for team members on the claude.ai Free plan. No Team or Enterprise features are assumed: no project sharing, no org-wide skills, five projects max.

Claude Chat does not read the repo by itself. The steps below load the **entire repository** into one project, so the model has the real files — `AGENTS.md`, both skills, every module and its README, the tests, the contracts — instead of guessing from descriptions.

## What you get, and what you do not

| You get | You do not get |
|---|---|
| Every repo file in project knowledge, kept fresh with Sync | A live checkout: knowledge is a snapshot |
| Both project skills, auto-triggered by their descriptions | Running `make test` / `make lint` — chat cannot execute code |
| Draft docs, doc reviews, proposed patches grounded in real files | Verified code. Chat output is a proposal, never "tested" |

Anything that changes `src/`, `tests/`, or `scripts/` still gets applied and verified in a real checkout. Chat plans, reviews, and proposes.

## Free plan constraints

| Constraint | Consequence |
|---|---|
| 5 projects maximum | Use one project for this repo; don't spend slots on throwaway projects |
| No project sharing | Every member repeats the setup below (~10 min) |
| No org-wide skill provisioning | Every member uploads both skills themselves |
| Tighter message limits | Batch questions; do not use chat as a build loop |
| Private repo needs app access granted | The Data-Science-Club-ELTE org admin must approve once |

## Before you start

- A claude.ai Free account, signed in.
- Repo: https://github.com/Data-Science-Club-ELTE/MOL-BUBI-Analysis
- If you cannot see the repo in the GitHub picker, the Claude GitHub app lacks access to the org. An org admin grants it once (GitHub → Settings → Applications → Claude → Organization access → Grant). You cannot fix this yourself.

## One-time setup (about 10 minutes)

### 1. Turn on code execution

Settings → Capabilities → enable **Code execution and file creation**. Skills do not exist without it, and the UI does not tell you that later.

### 2. Create the project and attach the whole repo

1. **Projects → New project**, name it `MOL Bubi`.
2. In **Project knowledge**, click **+** (upper right) → **GitHub**.
3. Search `Data-Science-Club-ELTE/MOL-BUBI-Analysis`.
4. Select the **repository root** so all files are imported — the whole repo is about 80 files, roughly 1 MB. That includes `AGENTS.md`, `CLAUDE.md`, `skills/`, `docs/`, `src/`, `tests/`, `scripts/`, `config/`, `Makefile`, `pyproject.toml`.
5. Confirm the picker shows the file count and adds them. If it warns about size or refuses, keep the root but deselect `uv.lock`, `data/`, and `skills/packages/*.zip` — those are the only bulky, irrelevant entries.
6. Click **Sync**.

### 3. Verify the import

Ask, in the new project:

```text
List the top-level directories and files you can read in this project, and confirm
whether src/bubi/contracts/schemas.py and skills/code-simplifier.md are readable.
```

Expected: `AGENTS.md`, `CLAUDE.md`, `Makefile`, `README.md`, `bubi-technical-design.md`, `config/`, `data/`, `docs/`, `scripts/`, `skills/`, `src/`, `tests/`, plus a yes for both named files. If anything is missing, re-open **Configure files** and add it, then Sync again.

### 4. Upload the two skills

1. Download [`skills/packages/technical-writing.zip`](../skills/packages/technical-writing.zip) and [`skills/packages/code-simplifier.zip`](../skills/packages/code-simplifier.zip).
2. **Customize → Skills → Add**, upload each ZIP unchanged. The archive already contains `<name>/skill.md`; do not unzip or rename it.
3. Confirm both are listed and toggled **on**.

Known risk: `technical-writing`'s description is 268 characters against a 200-character cap, so its upload may be rejected. If that happens, tell Ismail to trim the description and rebuild the ZIP — do not edit the skill yourself.

### 5. Paste the custom instructions

Project settings → **Instructions** → paste exactly:

```text
Follow AGENTS.md, which is in project knowledge — canonical rules, read it first.
Docs: use the technical-writing skill.
Code: implement, get make test + make lint green, then use the code-simplifier
skill as a second pass on files touched only. Chat cannot run make: return a
patch, never claim it is verified.
Sync before each session; project knowledge is a snapshot.
```

### 6. Smoke-test it

Failures are silent: Claude never says "that skill is missing", it just answers generically. Run all three and check each expected result.

| Prompt | Expected |
|---|---|
| "Which skills do you have, and what is the first rule in AGENTS.md?" | Names both skills, quotes the skill-loading rule |
| "Which file defines the Pandera schemas, and which tables? Do not open anything else." | Answers `src/bubi/contracts/schemas.py` with real table names |
| "Use the code-simplifier skill on this snippet: `return [x for x in items if x is not None]`" | Applies the second-pass rule, returns a patch, makes no verification claim |

If a prompt fails: expand the response's thinking and check whether the skill loaded; if not, re-upload it and name the skill explicitly in the prompt.

## Daily use

1. Click **Sync** on the GitHub source before you start. The import does not update itself.
2. Ask inside the project, never in a loose chat — instructions and knowledge belong to the project.
3. For code, ask for a **patch**, then apply and verify it in a real checkout.

Copy-paste prompts:

```text
/ Doc draft
Write <document type> for <subject>. Audience: <who reads it>. Sources: the files
already in this project. Follow the technical-writing skill. Every command must
exist in the Makefile or .github/workflows/ci.yml.
```

```text
/ Simplification pass
Use the code-simplifier skill on the diff below. Behavior must not change:
signatures, public names, outputs, and Pandera schemas stay frozen. Return a
unified diff plus one line per edit explaining why it is behavior-preserving.
Flag anything you are unsure about instead of guessing.
```

```text
/ Contract check before implementing
Read the README and tests for <module>. List its input contract, output contract,
and the tests that must keep passing. Do not write code yet.
```

The third prompt is the one that replaces a missing local checkout: it forces the model to read the module's real contract before proposing code.

## After any simplification

- [ ] Applied in a real checkout, not only in chat.
- [ ] `make test` passes.
- [ ] `make lint` passes.
- [ ] Diff touches only in-scope files; Pandera schemas unchanged.
- [ ] Commit message says behavior-preserving, or explains what changed.

If tests or lint fail, revert the patch. Do not "fix forward" from a chat suggestion.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Skill never fires | Description mismatch; failures are silent | Name the skill in the prompt, check it is toggled on |
| Answers about files that changed | Knowledge is a snapshot | Click **Sync** |
| Only some files appear | Picker selection incomplete or size warning | **Configure files** → add missing paths → Sync |
| Repo not in the GitHub picker | Claude app has no org access | Org admin grants it; retry after approval |
| "I can't run that" | Chat has no execution | Ask for a patch; run `make` locally |
| Skills greyed out or upload blocked | Code execution off | Settings → Capabilities → enable it |
| Upload rejected | Wrong archive shape, or description over 200 chars | Use `skills/packages/` unchanged; for `technical-writing`, ask Ismail to trim |

## Rules that still apply in chat

- Do not edit `skills/*.md` — report a bad skill instead.
- Do not call chat output verified. Only a passing `make test` + `make lint` in a checkout counts.
- Cite commands only from the `Makefile` or `.github/workflows/ci.yml`.
