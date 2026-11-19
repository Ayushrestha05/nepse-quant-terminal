---
title: Market Data Ingestion
tags: [component, data]
---

# Market Data Ingestion

```bash
python setup_data.py                                          # ~13 MB snapshot
python scripts/ingestion/deterministic_daily_ingestion.py     # after close
python setup_data.py --scrape --days 90
```

Calendar: `backend/quant_pro/nepse_calendar.py` (Mon–Fri default; `NEPSE_TRADING_WEEK=sun_thu` for legacy).

**Persist-first:** prices/quotes already incremental via `get_dynamic_data`. Gold/silver and rainfall ingest from `max(date)+1` unless `--force`. Sentiment skips sources that already have today's `sentiment_scores`. Earnings `skip_existing` skips symbols that already have the latest FY/Q in DB. Helpers: `backend/quant_pro/ingest_cache.py`. Cursor rule: `data-persist.mdc`.

When connected, Lookup / floorsheet / briefing prefer website — see [[Website Connect]]. Storage: [[Data and Config]]. Related: [[News Sentiment Pipeline]].
