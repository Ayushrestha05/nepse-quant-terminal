---
title: Market data coverage and GUI refresh
date: 2026-10-02
tags:
  - change
  - desktop
  - data
---

# Market data coverage and GUI refresh

## What changed

- Refreshed the desktop shell with native themed navigation, page headings, consistent spacing, and visible loading and empty states.
- Market now includes every current quote, an all-stored-symbol view with last price dates, coverage details, missing recent months, and a user-started history update with progress, cancellation, and per-symbol errors.
- Added paged tables with visible row totals, full paper trade and order histories, complete symbol lookup history, and restoration of the last saved Model Research result.
- Kept local views on a separate worker from heavier signals, research, rates, agent analysis, and ingestion work; optional rate sources now report their errors while retaining successful results.

## Why

The previous Market view stopped at 100 of 279 current symbols. The local database contained no May–September 2026 price history and benchmark data stopped on 2026-04-15, so the missing coverage was not visible from the UI.

## Purpose

Make the desktop app easier to navigate and let users see which data is present, what is stale, and whether a requested history update filled the gaps.

## Verification

- All `343` unit tests passed, including the optional-source reporting regression check.
- Linux Tk GUI smoke check built all 11 views and verified paging across a synthetic 205-row table. A read-only check of the local snapshot found 279 current quotes and missing price bars from May through September 2026.
- Local data-load check: current Market assembled 279 rows in `0.05s`; all-stored view assembled 406 rows in `0.04s`. The check process peaked at `81 MiB` RSS. The live provider update was not run.
- History progress, partial failures, and cancellation are covered by synthetic ingestion tests. The provider update itself remains user-started from Market.

## Related

- [[Home]]
- [[2026-10-02-market-data-correctness]]
- [[2026-10-02-desktop-gui]]
- [[Feature Change]]
