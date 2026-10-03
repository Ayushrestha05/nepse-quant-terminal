---
title: Clear desktop pagination labels
date: 2026-10-03
tags:
  - change
  - feature
  - desktop-gui
---

# Clear desktop pagination labels

## What changed

- Desktop tables show row ranges as `Rows 1 to 100 of 290`.
- The shared pager clamps page numbers when the data shrinks and disables navigation when there are no rows.
- Dashboard regression tests and the GUI smoke check cover page labels, visible row counts, bounds, and navigation states.

## Why

The compact range `1–100` could be read as `1100`, obscuring how many rows are visible.

## Purpose

Make table ranges easy to read and keep navigation aligned with the available rows.

## Verification

- Focused desktop dashboard tests: 20 passed.
- Desktop GUI smoke check: passed on the host display.
- Full unit suite: 373 passed.
- Internal links in the updated vault indexes and this note resolve.

## Related

- [[2026-10-03-desktop-live-logs|Collapsible desktop logs]]
- [[2026-10-02-desktop-gui|Desktop GUI]]
