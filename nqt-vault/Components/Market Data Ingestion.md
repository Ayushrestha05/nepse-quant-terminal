---
title: Market Data Ingestion
tags: [component, data]
---

# Market Data Ingestion

```bash
python setup_data.py                                          # ~13 MB snapshot
python setup_data.py --indices --proxy-only                   # NEPSE + 13 sector sub-indices (2020+)
python scripts/ingestion/deterministic_daily_ingestion.py     # after close
python setup_data.py --scrape --days 90
python -m backend.quant_pro.data_scrapers.ipo_ingestion --proxy-only
python -m backend.quant_pro.data_scrapers.floorsheet_ingestion --date-level --proxy-only --workers 4 --rps 1.0 --start 2020-01-01 --end 2026-11-20
```

Calendar: `backend/quant_pro/nepse_calendar.py` (Mon–Fri default; `NEPSE_TRADING_WEEK=sun_thu` for legacy).

**Proxy pool (`proxy_pool.py`):** All historical backfills support `--proxy-only` (`NQT_PROXY_ONLY=1`), rotating health-checked HTTPS proxies from `NQT_PROXIES` or public GitHub lists (cached 30 min in `data/runtime/healthy_proxies.txt`) with strict no-host-IP fallback (see [[Decision Log]] ADR-004).

**Floorsheet split:** Raw trades land in `data/floorsheet_raw.db`; `broker_summary`, `broker_signal_scores`, `broker_signals_v2`, `broker_microstructure`, and `floorsheet_scrape_log` land in `data/nepse_market_data.db`. Trading days come from distinct `stock_prices` dates and already-logged dates are skipped.

**IPO / FPO listings:** `ipo_ingestion.py` populates `ipo_listings` from ShareSansar (`existing-issues` JSON API) and Merolagani (`Ipo.aspx?type=past`), comparing official `listing_date` against `stock_prices` first-trading-day proxy (`--compare`).

**Persist-first:** prices/quotes already incremental via `get_dynamic_data`. Gold/silver and rainfall ingest from `max(date)+1` unless `--force`. Sentiment skips sources that already have today's `sentiment_scores`. Earnings `skip_existing` skips symbols that already have the latest FY/Q in DB. Helpers: `backend/quant_pro/ingest_cache.py`. Cursor rule: `data-persist.mdc`.

When connected, Lookup / floorsheet / briefing prefer website — see [[Website Connect]]. Storage: [[Data and Config]]. Related: [[News Sentiment Pipeline]].
