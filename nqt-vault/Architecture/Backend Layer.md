---
title: Backend Layer
tags: [architecture, backend]
---

# Backend Layer

| Package | Role | Links |
|---|---|---|
| `backend/trading/` | Paper execution, TUI engine, strategy registry, live/paper trackers | [[Paper Trading]], [[Strategy Registry]] |
| `backend/backtesting/` | `simple_backtest.py` signals + runner | [[Signal Engine]] |
| `backend/agents/` | LLM providers, tools, briefs | [[AI Analyst]] |
| `backend/nepse_agents/` | Evidence-gated paper agent graph | [[Nepse Agents Graph]] |
| `backend/market/` | Kalimati / rates helpers | [[Tab Rates]] |
| `backend/quant_pro/` | Calendar, research, scrapers, control plane | [[Market Data Ingestion]] |
| `backend/risk/` | Risk helpers | [[Paper Trading]] |
| `validation/` | Institutional validation battery | [[Validation Suite]] |

Upstream: [[Apps Layer]]. See [[Architecture Overview]].
