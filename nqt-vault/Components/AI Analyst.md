---
title: AI Analyst
tags: [component, ai]
---

# AI Analyst

`backend/agents/` — Ollama / OpenAI / Anthropic (+ optional Gemma MLX, Claude CLI). Setup: `./nqt-connect ai setup` → [[AI Setup]].

- Context: watchlist, paper book, strategy picks
- Tools: prices, history, news/filings, movers (read-only, capped; `NQT_AGENT_TOOLS=0` disables)
- Proactive briefs (Nepal TZ schedule); `/brief`, `/proactive off`

UI: [[Tab Agents]]. Sibling: [[Nepse Agents Graph]] for multi-agent paper workflow.
