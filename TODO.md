# TODO

Deferred data backfills and strategy follow-ups for NEPSE Quant Terminal.

## Data Backfills

- [x] **Backfill official NEPSE sector index history** (`benchmark_index_history` backfilled `2019-12-31` → `2026-11-20` across 14 indices, 23,166 rows) and topped up `NEPSE` in `stock_prices` through `2026-11-20` (`setup_data.py --indices --proxy-only`; `load_symbols()` now always includes `NEPSE`).
- [x] **Scrape real IPO / FPO listing dates** (`backend/quant_pro/data_scrapers/ipo_ingestion.py` -> `ipo_listings` table: 908 ShareSansar + Merolagani records with official `listing_date`s; 51 non-IPOs filtered out of `ipo_momentum`; re-backtested across all 3 `CAPITAL_SCENARIOS`).
- [ ] **Complete multi-year floorsheet and broker history backfill** *(scraper, separate `data/floorsheet_raw.db`, 4 aggregate tables including `broker_microstructure`, and `--proxy-only` support are implemented and verified; run unattended 1–2 day resumable job to reach `2020-01-01..present`)*:
  ```bash
  .venv/bin/python -u -m backend.quant_pro.data_scrapers.floorsheet_ingestion --date-level --proxy-only --workers 4 --rps 1.0 --start 2020-01-01 --end 2026-11-20
  ```
- [ ] **Complete multi-year news and sentiment history backfill** *(resumable Merolagani `newsID` walk from `55000`, UTF-8 decoding, `xlm-roberta` batch scoring, and `--proxy-only` support are implemented and verified; run unattended 1–2 day resumable job to reach `2020-01-01..present`)*:
  ```bash
  .venv/bin/python -u -m backend.quant_pro.data_scrapers.sentiment_ingestion --backfill --start-id 55000 --model xlm-roberta --batch-size 64 --rps 1.0 --proxy-only
  ```

## Deferred Strategies (Implemented — Re-run Suite Once Multi-Year Backfills Land)

- [ ] **Broker concentration / informed trading strategy** (`nepse_informed_trading`): implemented (`generate_informed_trading_signals_at_date`, registered in `data/strategy_registry/builtin/nepse_informed_trading.json`, wired into `simple_backtest.py` and `run_strategy_suite.py`). Run `scripts/validation/run_strategy_suite.py --only nepse_informed_trading --force` once floorsheet backfill populates `broker_signals_v2` (shortened IS window auto-labelled if data starts post-`2020-01-01`).
- [ ] **News sentiment strategy** (`nepse_nlp_sentiment`): enabled (`data/strategy_registry/builtin/nepse_nlp_sentiment.json`, wired into `run_strategy_suite.py`). Run `scripts/validation/run_strategy_suite.py --only nepse_nlp_sentiment --force` once news backfill populates `sentiment_scores`.
