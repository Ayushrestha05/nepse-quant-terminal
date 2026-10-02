---
title: Open-source walk-forward model research
date: 2026-10-02
tags:
  - change
  - research
---

# Open-source walk-forward model research

## What changed

- Added a scikit-learn logistic ranker that compares the existing candidate ranking with a model-ranked paper backtest.
- Added rolling 504-trading-day training windows and non-overlapping 63-day test windows. Training excludes candidate outcomes that mature on or after the test start.
- Added past-only market and signal features, NEPSE fees, configurable slippage, comparable out-of-sample portfolio runs, period metrics, trade records, and progress/cancellation hooks.
- Added optional score overrides to the shared backtest ranker. Existing callers retain their previous ranking by default.
- Kept the model isolated to research runs; paper trading is unchanged.

## Why

The project needed an open-source alternative to hosted JEV access for testing whether historical signals could be ranked more profitably without look-ahead leakage or pretending research scores were live decisions.

## Purpose

Let a user compare baseline and model portfolios over identical out-of-sample dates, including transaction fees and adjustable slippage, while retaining the current ranking as a control.

## Verification

- `python -m py_compile` passed for the changed backend and test modules.
- `git diff --check` passed.
- Added tests for point-in-time features, fees/slippage in labels, outcome purging at fold boundaries, retention of unlabeled test candidates, and score override ordering.
- The unit suite could not run on this host: its system Python is 3.14 (outside the repository's supported 3.10–3.13 range), and the installed test/runtime dependencies are incomplete. CI has the supported dependency installation workflow.

## Known limit

Labels use a fixed holding horizon with NEPSE fees and slippage. Portfolio exits still use the configured backtest stop, target, and holding rules, so candidate labels are a ranking target rather than a promise that every portfolio trade exits at the label horizon.

## Related

- [[Home]]
- [[Feature Change]]
