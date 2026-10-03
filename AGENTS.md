# Repository workflow

- Before changing code, inspect `git status` and preserve unrelated user changes.
- Start each new task on a `codex/<short-slug>` branch created from `main`; keep unrelated user work out of the task branch.
- Treat `docs/` as the Obsidian vault root. Keep its root index current and use Obsidian wikilinks for notes within the vault.
- For every coherent feature, bug fix, or documentation change, add or update a note in `docs/project-vault/Changes/` using `docs/project-vault/Templates/Feature Change.md`.
- Each note must say what changed, why it changed, its purpose, and how it was checked. Link related notes with Obsidian wikilinks.
- Keep the note and implementation in the same Git commit so Git history records the exact file history. Do not put a commit hash in the note; the commit contains the note itself.
- Every behavior-changing feature or bug fix needs a focused regression test that fails if the behavior breaks. Run the full unit suite before merging; use GUI smoke checks for UI changes and link checks for documentation changes.
- After focused checks pass, stage only paths belonging to that change, inspect the staged diff, and create a local commit. Never stage unrelated or pre-existing untracked files.
- After all checks pass, merge the task branch into local `main` (fast-forward when possible). Push completed, checked changes when the user has authorized pushing. Never force-push or push incomplete work; stop on authentication failure or incompatible remote history.
- Do not create a commit for incomplete work or failing checks; finish or record the remaining issue first.
