---
title: Collapsible desktop logs
date: 2026-10-03
tags:
  - change
  - desktop-gui
---

# Collapsible desktop logs

## What changed

- Added a bottom Logs button that expands a scrollable panel and retains the latest 1,000 app-session entries while collapsed.
- Captured task lifecycle and status updates, Python INFO-and-higher records, research progress, and all price-history subprocess output. Entries show timestamps and task, history, or logger categories, with severity colors and text labels.
- Added focused coverage for buffer retention, severity tags, background logging, and history subprocess output.

## Why

The desktop GUI showed brief status messages but did not provide a single place to inspect refresh and background task activity.

## Purpose

Let users inspect current-session app activity and diagnose refresh or task failures from any desktop page.

## Verification

- Focused desktop dashboard tests passed (14 tests); the full unit suite passed (367 tests).
- Internal links in the updated vault indexes and this note resolve.
- The GUI smoke check now covers panel expansion, category labels, and warning color tags. It could not run locally because Tk cannot connect to the configured `:0` display; CI runs this check under Xvfb on Linux.

## Related

- [[2026-10-03-local-data-issues-and-daily-refresh|Market data issues and daily refresh]]
- [[2026-10-02-desktop-gui|Desktop GUI]]
