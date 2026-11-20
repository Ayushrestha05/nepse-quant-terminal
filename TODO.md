# TODO

Deferred data backfills and strategy follow-ups for NEPSE Quant Terminal.

## Data Backfills

- [ ] **Backfill floorsheet and broker history** (`floorsheet_trades`, `broker_summary`, `broker_signal_scores` in `data/nepse_market_data.db` are currently empty).
- [ ] **Backfill news and sentiment history** (`news` and `sentiment_scores` tables are currently empty).
- [ ] **Scrape real IPO / FPO listing dates** from CDSC / Merolagani / ShareSansar to replace the post-2017 first-trading-day proxy used by `ipo_momentum`.
- [ ] **Backfill official NEPSE sector index history** (`benchmark_index_history` currently has only 65 days, Dec 2025–Apr 2026) and top up the `NEPSE` index past `2026-04-15`.

## Deferred Strategies (Blocked on Data Backfills)

- [ ] **Broker concentration / informed trading strategy** (`informed_trading`): implement and backtest across all 3 `CAPITAL_SCENARIOS` once `floorsheet_trades` / `broker_summary` / `broker_signal_scores` have multi-year history.
- [ ] **News sentiment strategy** (`nlp_sentiment`): implement/enable backtesting across all 3 `CAPITAL_SCENARIOS` once `news` and `sentiment_scores` have multi-year history.
