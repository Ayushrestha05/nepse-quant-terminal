---
title: Decision Log
tags: [history, adr]
---

# Decision Log

Accepted ADRs are immutable; supersede with a new number.

## ADR-001 — Obsidian vault at `nqt-vault/`

- **Status:** Accepted (2026-11-19)
- **Context:** Need a linked knowledge base that explains the app and tracks later changes in Obsidian Graph. The old `docs/` folder-as-vault mixed runbooks/media with notes.
- **Decision:** Dedicated vault at repo-root `nqt-vault/` with wikilinked MOC, managed via Obsidian CLI (`obsidian vault=nqt-vault …`).
- **Consequences:** Product knowledge lives in-repo; open vault named `nqt-vault` in Obsidian.

## ADR-002 — Graphify artifacts are local-only

- **Status:** Accepted (2026-11-19)
- **Context:** `graphify-out/` regenerates deterministically and pollutes PR review / merges.
- **Decision:** Gitignore artifacts; never review them on GitHub; on conflict delete and recreate with `graphify extract . --code-only` (+ `cluster-only` as needed).
- **Consequences:** Agents rebuild graphs locally; vault summarizes via [[Graphify]].
