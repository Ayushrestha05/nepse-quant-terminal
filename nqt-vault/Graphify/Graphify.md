---
title: Graphify
tags: [graphify, agents, moc]
aliases: [Graphify]
---

# Graphify

Local code knowledge graph (AST, no vector DB). Package `graphifyy`, command `graphify`.

## Commands

```bash
graphify extract . --code-only     # build (no API key)
graphify cluster-only . --no-label # GRAPH_REPORT.md + graph.html
graphify update .                  # after code edits
graphify query "paper execution"
graphify path "dashboard_tui" "paper_execution"
graphify explain "StrategyRegistry"
```

Outputs (local only, **not in git / not in PR review**):

```
graphify-out/
├── graph.json
├── graph.html
└── GRAPH_REPORT.md
```

## Agent usage

- Cursor rule: `.cursor/rules/graphify.mdc` (always apply) — query before blind grep.
- Skills: `.cursor/skills/graphify/SKILL.md`, `.agents/skills/graphify/SKILL.md`.
- Conflict policy: [[Graphify Git Policy]] — delete artifacts, recreate.

## Export into this vault

```bash
graphify export obsidian --dir nqt-vault/Graphify/export
```

Related: [[Developer Workflow]], [[Architecture Overview]], [[Change Log]].
