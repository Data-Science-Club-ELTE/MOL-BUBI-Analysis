# Claude Chat setup (Free plan)

Five minutes, once. Then click **Sync** before each session.

## Setup

1. **Settings → Capabilities → Code execution ON.** Skills don't work without it, and nothing tells you that later.
2. **Projects → New project** → name it `MOL Bubi` → in Project knowledge click **+** → **GitHub** → pick `Data-Science-Club-ELTE/MOL-BUBI-Analysis` → select the **repo root** (whole repo, ~1 MB) → **Sync**.
   Can't find the repo? An org admin must grant the Claude GitHub app access. Not you.
3. **Customize → Skills → Add** → upload both zips from [`skills/packages/`](../skills/packages/) unchanged (don't unzip or rename).
4. **Project → Instructions** → paste:

   ```text
   Follow AGENTS.md in project knowledge. Read it before working.
   Docs: use the technical-writing skill.
   Code: implement, get make test + make lint green, then use the
   code-simplifier skill on touched files only. Chat can't run make:
   return a patch, never claim it's verified.
   ```

5. **Check it worked** — run this, and expect both skills named plus real file paths:

   ```text
   Which skills do you have? List the top-level files you can read, and confirm
   src/bubi/contracts/schemas.py and skills/code-simplifier.md are readable.
   ```

   Wrong or vague answer means the import or upload failed. Fix now — Claude never warns you.

## Using it

- **Before every session: click Sync.** Knowledge is a snapshot, not a live repo.
- **Docs** → just ask, using the technical-writing skill.
- **Code** → ask for a patch, apply it yourself, run `make test` + `make lint`. Chat can't execute, so its output is never verified.

## If it misbehaves

| Problem | Fix |
|---|---|
| Skill never used | Name it in the prompt; check it's toggled on |
| Answers from old code | Sync |
| Files missing | Project knowledge → Configure files → add → Sync |
| `technical-writing` upload rejected | Its description is 268 chars vs a 200-char cap — ask Ismail to trim it |

Two rules: don't edit `skills/*.md` yourself, and only a real `make test` counts as verification.
