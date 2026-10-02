---
title: Compact cross-platform desktop GUI
date: 2026-10-02
tags:
  - change
  - desktop
---

# Compact cross-platform desktop GUI

## What changed

- Added a native `tkinter.ttk` desktop app with lazy views for Market, Portfolio, Signals, Lookup, Agents, Orders, Watchlist, Rates & Commodities, Account, Strategies, and Model Research.
- Reused the existing paper execution service, per-account paper engines, strategy registry, market database, and runtime files. Research runs in a single background worker and never changes paper-trading decisions.
- Added baseline/model out-of-sample metrics, equity curves, per-window and per-trade tables, adjustable slippage, progress, cancellation, and a saved `latest.json` result.
- Validated order and NAV inputs so malformed or non-finite numbers cannot enter paper account state.
- Made the Python and OS launchers open the GUI by default; `--tui` retains the Textual terminal app. Added GUI widget smoke checks to the Windows, macOS, and Linux CI matrix.
- Updated the README and launch guide for the desktop app.

## Why

The terminal-only interface was uncomfortable for the user. A native toolkit avoids a browser or Electron runtime and keeps the installation footprint small. Long-running data loads and research should not freeze the interface on a modest laptop.

## Purpose

Provide a familiar desktop workflow for existing paper-trading features and make the walk-forward research comparison usable without a terminal, while keeping model output research-only.

## Verification

- Python compilation passed for the GUI, launcher, and backtesting modules.
- `sh -n` passed for the macOS shell launchers; `git diff --check` passed.
- `python scripts/launch/bootstrap.py --help` confirmed the optional `--tui` fallback.
- Added unit coverage for finite numeric input handling.
- CI now creates the GUI and all 11 views under Xvfb on Linux and directly on macOS and Windows. This host has no X display server, so the Tk widget smoke command could not be run locally.
- Full model tests and research memory/responsiveness measurement remain unavailable locally because this checkout has no market database, the system Python is outside the supported range, and its runtime lacks the test/model dependencies. The synthetic timing/cost assertions for the research backend passed in the prior feature check.

## Related

- [[Home]]
- [[2026-10-02-model-research]]
- [[Feature Change]]
