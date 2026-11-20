---
title: Baseline Backtest
tags: [validation, baseline, paper]
status: complete
---

# Baseline Backtest

Paper simulation of the built-in **C5** strategy (`data/strategy_registry/builtin/default_c5.json`) vs NEPSE buy-and-hold. For the step-by-step execution pipeline see [[Backtesting Process]].

## How to reproduce

```bash
# clean env if Cursor AppImage pollutes LD_LIBRARY_PATH — use project .venv
.venv/bin/python setup_data.py
.venv/bin/python setup_data.py --scrape --days 230   # top-up after bundled cutoff
.venv/bin/python scripts/validation/run_baseline.py --force
```

Outputs (gitignored): `data/runtime/baselines/<run_date>/` — `summary.txt`, `metrics.json`, `trades.csv`, `nav.csv`.

Cross-check cache: `data/runtime/crosscheck/`.

## Window and rules

- **Window:** `2020-01-01` → `2026-11-19` (1,557 trading days; 405 symbols; 504,616 price rows)
- **Runtime:** **4m 14s** (`254.46s` total after routing per-symbol lookups through `symbol_cache` and guarding `init_db()`; previously ~5.5–6h)
- **Prices:** adjusted (Merolagani `isAdjust=1`)
- **Exclude:** symbols where menaceXnadin overlap has >5% of days with close mismatch >1%
- **Engine:** `run_backtest(..., exclude_symbols=…)` fees + stops + regime filter; **no slippage**

## Metrics (`2020-01-01` → `2026-11-19`)

### NAV-based sizing across all 3 standard scenarios (ADR-003, [[2026-11-20_1108/C5 Baseline (NAV Sizing)|C5 Baseline (NAV Sizing)]])

| Scenario | Contributed | Final NAV | TWR CAGR | XIRR | Sharpe | Max DD | Trades | Fees % Inv | OOS CAGR (25-26) | OOS Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lump_10l` (10L Lump Sum) | NPR 1,000,000 | NPR 2,803,468 | **+16.14%** | +16.14% | **0.95** | -54.62% | 196 | 70.70% | +15.79% | 1.26 |
| `lump_1l` (1L Lump Sum) | NPR 100,000 | NPR 175,149 | **+8.48%** | +8.48% | **0.54** | -54.54% | 171 | 68.17% | +12.12% | 0.88 |
| `sip_5k` (5K + 5K/BS Month) | NPR 415,000 | NPR 507,799 | **+5.27%** | **+5.86%** | **0.38** | -53.58% | 165 | 19.25% | +15.11% | 1.22 |

### Legacy fixed-capital sizing (`2020-01-01` → `2026-11-19`, [[2026-11-20 - C5 Baseline]])

| Metric | C5 (`default_c5`, legacy) | NEPSE buy-and-hold (to `2026-04-15`) |
| --- | ---: | ---: |
| Start → End NAV / Close | NPR 1,000,000 → 2,210,873 | 1,169.50 → 2,833.60 |
| Total return | **+121.09%** | +142.29% |
| Annualized (CAGR) | **+12.21%** | +15.12% |
| Volatility (ann.) | **12.07%** | — |
| Sharpe / Sortino | **1.07** / **1.72** | — |
| Max drawdown | **-26.14%** (875d) | -43.25% |
| Trades / Win rate / PF | **209** / **38.8%** / **1.63** | — |
| Fees paid | **NPR 360,959** | — |

- **Excluded symbols (menaceXnadin cross-check, 21 symbols):** `0` (`none`).

## Issues tracked

1. **NEPSE index stops at `2026-04-15`** *(open)*: `stock_prices WHERE symbol='NEPSE'` max date = `2026-04-15`, while 352 stocks extend to `2026-11-19`. Must top up `NEPSE` before trusting benchmark numbers post-`2026-04-15`.
2. **Runtime bottleneck** *(resolved 2026-11-20)*: ~11 min per 50 trading days (~5.5–6h for 1,557 days) dropped to **~7.8s per 50 trading days (4m 14s total)** by routing every per-symbol lookup in `backend/backtesting/simple_backtest.py` through `symbol_cache` (`_history`) and calling `init_db()` once per DB path in `backend/quant_pro/event_layer.py`. Verified by `tests/test_backtest_parity.py` (76d Q1-2023 window: `489.45s` → `17.75s`, identical trades and NAV).

## Caveats

- In-sample relative to C5 parameter history (see README disclaimer).
- No slippage; limit-locked days still fill.
- Survivorship bias: delisted stocks missing from the universe.
- Corporate actions only refreshed for top 20 symbols (prices are already `isAdjust=1`).

## Data sources & reports

- Process guide: [[Backtesting Process]]
- Data sources: [[External Market Data Sources]]
- Run reports: [[Backtest Reports]] (latest: [[2026-11-20 - C5 Baseline]], prior partial: [[2026-11-20 - C5 Baseline (Partial)]])

Related: [[Backtesting Process]], [[Validation Suite]], [[Signal Engine]], [[News Sentiment Pipeline]], [[Change Log]].
