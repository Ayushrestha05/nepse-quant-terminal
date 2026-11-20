---
title: External Market Data Sources
tags: [data, sources, baseline]
---

# External Market Data Sources

Repos and mirrors used to build and validate the local `nepse_market_data.db` for paper backtests. None of these are official NEPSE feeds.

## Sources we use

| Source | URL | Use in NQT |
| --- | --- | --- |
| **Bundled DB (v3.0 release)** | [nlethetech/nepse-quant-terminal releases](https://github.com/nlethetech/nepse-quant-terminal/releases/tag/v3.0) (`nepse_data_public.db.gz`) | Primary bootstrap via `python setup_data.py`. Real adjusted-ish OHLCV through **2026-04-15**, plus quarterly earnings and corporate actions. |
| **Merolagani chart API** | `handlers/TechnicalChartHandler.ashx` with `isAdjust=1` via [`backend/quant_pro/vendor_api.py`](../../backend/quant_pro/vendor_api.py) | Incremental / full price top-up after the bundled cutoff (`setup_data.py --scrape`). Adjusted for bonus/rights/splits. |
| **menaceXnadin CSV mirror** | [menaceXnadin/nepse-historical-market-data-csv](https://github.com/menaceXnadin/nepse-historical-market-data-csv) | **Cross-check only.** Daily adjusted CSVs (ShareHub-sourced). Cached under `data/runtime/crosscheck/`. Symbols with >5% of overlapping days >1% close mismatch are excluded from the baseline universe. |
| **ShareSansar existing-issues JSON API** | `https://www.sharesansar.com/existing-issues?type=1..8&length=50` via `ipo_ingestion.py` | Official IPO, FPO, Right Share, and Mutual Fund issue + `listing_date` records stored in `ipo_listings` (max `length=50` per request). |
| **Merolagani Floorsheet & NewsDetail** | `Floorsheet.aspx`, `NewsDetail.aspx?newsID=<id>`, `Ipo.aspx?type=past` | Resumable historical floorsheet (2020+, raw → `data/floorsheet_raw.db`, aggregates → main DB), historical news ID walk (`55000..latest`), and past IPO backup cross-check. |
| **Public GitHub HTTPS proxy lists** | `proxifly/free-proxy-list`, `TheSpeedX/PROXY-List`, `monosans/proxy-list`, `vakhov/fresh-proxy-list` via `proxy_pool.py` | Free HTTPS proxy pool for `--proxy-only` scraping (health-checked over TLS against `https://merolagani.com/`, never falls back to direct IP). |

## Other public repos (not primary for this baseline)

| Source | URL | Notes |
| --- | --- | --- |
| Aabishkar2/nepse-data | https://github.com/Aabishkar2/nepse-data | ~370 company CSVs, mostly unadjusted; good archive, not used for C5 baseline. |
| SamirWagle/Nepse-All-Scraper | https://github.com/SamirWagle/Nepse-All-Scraper | Unadjusted prices + dividends/rights/floorsheet; useful for corp-action research later. |

## Pipeline (baseline)

1. Download bundled DB → `data/nepse_market_data.db`
2. Top up prices with Merolagani (`--scrape --days …`)
3. Refresh earnings (`scrape_all_earnings(skip_existing=True)`) and corporate actions as needed
4. Cross-check liquid symbols + NEPSE vs menaceXnadin adjusted CSVs
5. Run C5 via `scripts/validation/run_baseline.py`

Related: [[Baseline Backtest]], [[Market Data Ingestion]], [[Data and Config]], [[Validation Suite]].
