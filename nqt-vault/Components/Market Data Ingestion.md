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

When connected, Lookup / floorsheet / briefing prefer website — see [[Website Connect]]. Storage: [[Data and Config]].
