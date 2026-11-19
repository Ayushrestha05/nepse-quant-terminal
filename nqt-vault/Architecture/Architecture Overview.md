---
title: Architecture Overview
tags: [architecture, moc]
related:
  - "[[Apps Layer]]"
  - "[[Backend Layer]]"
  - "[[TUI Dashboard]]"
---

# Architecture Overview

Entry: `python -m apps.tui.dashboard_tui` (Textual TUI, 10 tabs, keyboard-first).

```
┌──────────────────────────────────────────────────────────────┐
│ Textual TUI · apps/tui/dashboard_tui.py · 10 tabs · keyboard │
└───────┬──────────────────────┬───────────────────────┬───────┘
        │                      │                       │
┌───────▼───────┐   ┌──────────▼──────────┐   ┌────────▼──────────┐
│ Local market  │   │ Paper trading       │   │ nepsequant.com    │
│ backend/market│   │ paper_execution.py  │   │ apps/cli/connect  │
└───────┬───────┘   └──────────┬──────────┘   │ apps/tui/io/      │
        │                      │              │   website_*.py    │
┌───────▼──────────────────────▼───────┐      └───────────────────┘
│ Signal engine · simple_backtest.py   │
└──────────────────────────────────────┘
```

## Layer map

| Layer | Path | Notes |
|---|---|---|
| UI | [[Apps Layer]] → [[TUI Dashboard]] | Tabs, state mixins, render |
| Connect | [[Website Connect]] | Shared paper book, lookup, strategies |
| Trading | [[Paper Trading]] · [[Strategy Registry]] | Local + website auto-trade |
| Research | [[Signal Engine]] · [[Validation Suite]] | Signals, backtests, GO/NO-GO |
| AI | [[AI Analyst]] · [[Nepse Agents Graph]] | Chat, briefs, evidence-gated paper workflow |
| Native | [[Native Floor Engine]] | Optional Rust floor metrics |
| Data | [[Data and Config]] | DB snapshot, registries, runtime |

Related repo docs: `docs/architecture/PROJECT_STRUCTURE.md`, root `README.md`.

See also: [[Change Log]], [[Graphify]].
