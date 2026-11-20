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

## ADR-003 — Account-value sizing, 3 standard capital scenarios, and separate `data/backtests.db`

- **Status:** Accepted (2026-11-20)
- **Context:** The original backtest engine sized positions off static `initial_capital` with a hard NPR 10,000 minimum position floor and saved trades only to gitignored `trades.csv`. Monthly SIP deposits sat idle in cash, small retail accounts (NPR 5,000 start) could never open a trade, and runs were not queryable across strategies or scenarios.
- **Decision:**
  1. Size positions from current account NAV (`nav / effective_max_positions_for_nav`), remove the NPR 10,000 floor, preserve the 10-share minimum lot and full NEPSE fees (including NPR 25 DP charge), and scale max concurrent positions for small accounts.
  2. Standardize every backtest on three `CAPITAL_SCENARIOS`: `lump_10l` (NPR 10L), `lump_1l` (NPR 1L), and `sip_5k` (NPR 5K start + NPR 5K on the first trading day of each BS month via `nepdate-core`), reporting both TWR and XIRR. Enforced via `.cursor/rules/backtest-scenarios.mdc`.
  3. Persist all runs, trades, daily NAV (`nav`, `cash`, `invested`), and contributions into a dedicated, gitignored SQLite database `data/backtests.db` (`backend/backtesting/results_store.py`), skipping unchanged `(strategy_id, scenario, config_hash, data_end, window)` runs unless `--force` is passed.
- **Consequences:** All historical baselines (including C5) are re-run under NAV sizing for comparability; legacy fixed-capital reports remain preserved as historical records in [[Backtest Reports]]. Every future strategy evaluation produces queryable trade ledgers across small and large retail Nepali accounts.

## ADR-004 — Separate `data/floorsheet_raw.db` and HTTPS-only proxy-only scraping

- **Status:** Accepted (2026-11-20)
- **Context:** Multi-year NEPSE floorsheet history (2020–present) comprises tens of millions of trade rows (~8–10 GB with indexes), which would bloat `data/nepse_market_data.db` and slow down daily queries. At the same time, multi-day historical scraping of Merolagani and ShareSansar must not originate from the host IP or silently fall back to direct requests when proxies fail.
- **Decision:**
  1. Store all raw `floorsheet_trades` in a dedicated, gitignored SQLite file `data/floorsheet_raw.db` (`NEPSE_FLOORSHEET_RAW_DB`), preserving trade-level pairs and prices so new microstructure/broker features never require re-scraping.
  2. Compute all four daily aggregate tables (`broker_summary`, `broker_signal_scores`, `broker_signals_v2`, `broker_microstructure`) into `data/nepse_market_data.db` during ingest; strategies (`informed_trading`) read only those aggregates.
  3. Route all historical scrapers through a shared HTTPS-only proxy pool (`backend/quant_pro/data_scrapers/proxy_pool.py`), health-checked against `https://merolagani.com/` with TLS verification (`verify=True`). In proxy-only mode (`--proxy-only` / `NQT_PROXY_ONLY=1`), raise `ProxyPoolError` rather than falling back to the host IP, reject non-HTTPS targets, and discard malformed HTML/rows.
- **Consequences:** Main DB stays compact and fast; raw floorsheet archives are preserved locally for future feature work; unattended backfills never leak the host IP. See [[Market Data Ingestion]], [[News Sentiment Pipeline]], [[External Market Data Sources]].
