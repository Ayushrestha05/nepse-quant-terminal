---
title: "Stock detail charts from Market"
date: 2026-10-03
tags:
  - change
  - desktop
  - market
---

# Stock detail charts from Market

## What changed

- Market stock rows open a reusable detail window with historical candlesticks, a close-price line option, moving averages, aligned volume, trading statistics, and cached financial analysis.
- Added a focused selection, history, chart, and stale-result regression suite and expanded GUI smoke coverage.

## Why

Market rows previously showed summary values without an immediate view of the selected company's historical price action or financial details.

## Purpose

Make locally stored market history and company analysis accessible from the Market tab.

## Verification

- `tests/unit/test_stock_detail.py`, `tests/unit/test_desktop_dashboard.py`, and `tests/unit/test_easy_launch.py`: 38 passed.
- Full `tests/unit` suite: 388 passed. Expanded Tk dashboard smoke check passed with candlestick and line charts, range selection, resizing, reuse, and reopening.

## Related

- [[Home]]
- [[2026-10-02-desktop-gui]]
- [[Feature Change]]
