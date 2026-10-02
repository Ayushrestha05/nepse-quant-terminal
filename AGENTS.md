# Repository workflow

- Before changing code, inspect `git status` and preserve unrelated user changes.
- For every coherent feature, bug fix, or documentation change, add or update a note in `docs/project-vault/Changes/` using `docs/project-vault/Templates/Feature Change.md`.
- Each note must say what changed, why it changed, its purpose, and how it was checked. Link related notes with Obsidian wikilinks.
- Keep the note and implementation in the same Git commit so Git history records the exact change. Do not put a commit hash in the note; the commit contains the note itself.
- After the focused checks pass, stage only paths belonging to that change, inspect the staged diff, and create a local commit. Never stage unrelated or pre-existing untracked files. Do not push unless the user asks.
- Do not create a commit for incomplete work or failing checks; finish or record the remaining issue first.
