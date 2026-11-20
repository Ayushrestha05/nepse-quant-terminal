---
title: Change Log
tags: [history, changelog]
---

# Change Log

Append-only. Newest first. Link components you touched.

## 2026-11-20

- [[Strategy Catalog]] + [[Signal Engine]] + [[Strategy Registry]] + [[Backtesting Process]] + [[Baseline Backtest]] + [[Backtest Reports]] + [[Decision Log]] (ADR-003): added 9 NEPSE-specific solo strategies (`book_closure_runup`, `ex_date_gap`, `circuit_continuation`, `ipo_momentum`, `sector_rotation`, `earnings_drift`, `calendar_festival`, `nrb_policy`, `lead_lag` in `backend/backtesting/nepse_event_signals.py` + `backend/quant_pro/nepal_calendar.py` powered by `nepdate-core==1.0.0rc1` / `nepdate-patro==1.0.0rc1`) and 5 combinations (`combo_event_driven`, `combo_trend`, plus 2020–2024 IS-selected `combo_top3_sharpe`, `combo_top5_sharpe`, `combo_c5_plus_best`). Switched `simple_backtest.py` to NAV-based equal-weight sizing, small-account position caps (removed NPR 10K floor, kept 10-share lot + realistic fees), BS month-start SIP contributions, TWR + XIRR metrics, and 3 mandatory `CAPITAL_SCENARIOS` (`lump_10l`, `lump_1l`, `sip_5k`, enforced by `.cursor/rules/backtest-scenarios.mdc`). Added dedicated trade store `data/backtests.db` (`backend/backtesting/results_store.py`), parallel runner `scripts/validation/run_strategy_suite.py`, multi-scenario `run_baseline.py`, unit tests (`tests/unit/test_capital_scenarios.py`, 5/5 passing), root `TODO.md` for deferred data backfills, and ran all 45 backtests (8,958 trades logged) producing 15 per-strategy reports, [[2026-11-20 - Strategy Comparison]] with log-scale NAV charts, and updated [[00 - Index]].
- [[Backtesting Process]] + [[Signal Engine]] + [[Baseline Backtest]]: routed all per-symbol price lookups in `backend/backtesting/simple_backtest.py` through `symbol_cache` (`_history` helper, eliminating full-table scans on unlisted symbols and uncached generators/filters) and guarded `init_db()` once per DB path in `backend/quant_pro/event_layer.py`. Added parity regression test (`tests/test_backtest_parity.py` + `tests/fixtures/c5_2023q1_reference.json`; `489.45s` → `17.75s`, identical trades & NAV). Re-ran full `2020-01-01` → `2026-11-19` C5 baseline in **4m 14s** (`254.46s`, down from ~5.5–6h): +121.09% total (+12.21% CAGR, Sharpe 1.07, Sortino 1.72, -26.14% Max DD, 209 trades, PF 1.63); logged [[2026-11-20 - C5 Baseline]] in [[Backtest Reports]] and added [[Backtesting Process]] guide with Mermaid flowchart linked from [[00 - Index]].
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
