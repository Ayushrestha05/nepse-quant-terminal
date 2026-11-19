---
name: nqt-vault
description: >-
  Maintain the NEPSE Quant Terminal Obsidian vault (nqt-vault/) with wikilinks
  for Graph view, and use Obsidian CLI to create/edit notes. Use when documenting
  the app, logging changes, opening the vault, or after shipping features.
---

# nqt-vault

## Paths

- Vault: `nqt-vault/` (repo root)
- CLI: `obsidian vault=nqt-vault <command>` (Obsidian app must be running; `cli: true` in config)

## Create / edit notes

```bash
obsidian vault=nqt-vault create path="Components/My Feature.md" content="# My Feature\n\nSee [[TUI Dashboard]]." overwrite
obsidian vault=nqt-vault search query="paper trading"
obsidian vault=nqt-vault unresolved
```

Prefer writing markdown files under `nqt-vault/` with `[[wikilinks]]` so the Obsidian Graph stays connected. Index: `00 - Index.md`.

## After EVERY completed task (mandatory)

Do this before saying the work is done — not optional, even for small fixes/rules/installs.

1. Append to `Project History/Change Log.md` (newest first) with `[[wikilinks]]`.
2. Touch or create linked Architecture/Components/Tabs/Guides notes; link new ones from `00 - Index.md`.
3. ADR if irreversible → `Decision Log.md`.
4. Optional session note: `Project History/YYYY-MM-DD - Title.md`.
5. Refresh code graph when structure changed: `graphify update .` (see graphify skill / `./scripts/ops/recreate_graphify.sh`).

Project rule: `.cursor/rules/nqt-vault.mdc` (`alwaysApply`).

## Conventions

See vault note `Guides/Vault Conventions.md`.
