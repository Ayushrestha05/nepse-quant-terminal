---
title: Change Log
tags: [history, changelog]
---

# Change Log

Append-only. Newest first. Link components you touched.

## 2026-11-20

- [[Graphify]]: refreshed code graph (`5,143` nodes, `14,253` edges, `204` communities), installed git hooks (`graphify hook install` — auto-rebuilds after every commit), and updated `.cursor/rules/graphify.mdc` + `.cursor/rules/nqt-vault.mdc` to require searching both `graphify` and `nqt-vault/` first for project information.
- Mandatory close-out rule (`.cursor/rules/nqt-vault.mdc`): added commit-on-completion step for verified changes (never stage Obsidian workspace state or runtime files).
- Created `nqt-vault/Backtest Reports/` with [[Backtest Reports]] run tracker and [[2026-11-20 - C5 Baseline (Partial)]], linked from [[00 - Index]] and [[Baseline Backtest]].
- [[Baseline Backtest]] + [[External Market Data Sources]]: added `exclude_symbols` to `run_backtest`, menaceXnadin cross-check (`scripts/validation/baseline_crosscheck.py` + unit test), and `scripts/validation/run_baseline.py`. Topped DB to `2026-11-19` (504,616 rows, 405 symbols; 0 symbols excluded). Partial C5 run stopped at day 1,150/1,557 (`2020-01-01` → `2025-02-10`): +109.45% (+15.56% CAGR, 160 trades, -22.07% checkpoint DD vs NEPSE +128.93% / -43.25% DD). Found `NEPSE` index missing post-`2026-04-15` and ~11 min/50-day runtime bottleneck.
- Vault close-out made mandatory (`.cursor/rules/nqt-vault.mdc` + [[Vault Conventions]]); agents must update [[Change Log]] before claiming done.
- Persist-first ingest: `.cursor/rules/data-persist.mdc` + `backend/quant_pro/ingest_cache.py` — skip/incremental for [[News Sentiment Pipeline]], gold/silver, rainfall, earnings `skip_existing` ([[Market Data Ingestion]], [[Data and Config]]).
- [[News Sentiment Pipeline]]: optional proxy/Firecrawl fetch, nepali-xlmr + fin-qwen + Ollama LLM scoring, no look-ahead in signal, IC script, handoff doc `docs/research/NEWS_SENTIMENT_PIPELINE.md`.
- Local Ollama default model → `qwen3:4b` ([[AI Setup]], [[AI Analyst]]).
- [[Nepse Agents Graph]]: bounded Dexter-style research validate loop (max 2 rounds).

## 2026-11-19

- Created [[00 - Index]] vault (`nqt-vault/`) documenting current app surface with wikilinks for Obsidian Graph.
- Bootstrap [[Graphify]]: project Cursor rule + `.agents` / `.cursor` skills; `graphify-out/` gitignored; conflict policy = delete + recreate.
- Session: [[2026-11-19 - Vault and Graphify Bootstrap]].

<!-- Template
## YYYY-MM-DD
- What changed — why — links to [[Component]] notes
-->
