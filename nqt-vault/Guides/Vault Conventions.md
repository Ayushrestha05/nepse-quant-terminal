---
title: Vault Conventions
tags: [guide, vault]
---

# Vault Conventions

- **Mandatory close-out:** after every completed task, append [[Change Log]] and update linked notes before claiming done (Cursor rule `nqt-vault.mdc`).
- **Wikilinks everywhere** (`[[Note]]`) so Obsidian Graph stays dense.
- **Living docs** undated under Architecture / Components / Tabs / Guides.
- **Session logs** dated `YYYY-MM-DD - Title` under Project History.
- **Change Log** — append-only bullets for later work (never rewrite history; supersede).
- **Decision Log** — `ADR-NNN`; accept once, supersede with a new ADR.
- Graphify HTML/JSON lives in repo `graphify-out/` (gitignored) — summarize into [[Graphify]] notes, don't commit artifacts.

Managed with Obsidian CLI: `obsidian vault=nqt-vault create|read|search|…` — see [[Obsidian CLI]].

Related: [[Market Data Ingestion]], [[News Sentiment Pipeline]].
