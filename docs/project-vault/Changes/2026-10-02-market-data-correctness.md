---
title: Market data correctness and cancellable ingestion
date: 2026-10-02
tags:
  - change
  - data
---

# Market data correctness and cancellable ingestion

## What changed

- Market changes now use a quote's previous close only when its quote belongs to the displayed Nepal session.
- Price bars are not compared across a gap longer than 14 calendar days; missing daily changes no longer count as unchanged in market breadth.
- The daily ingestion command accepts a cancel file and records a graceful stop as a partial run after the current symbol.

## Why

The local snapshot had no stock price bars from May through September 2026. Fresh October quotes were being compared to April closes, which showed a misleading market breadth.

## Purpose

Keep daily changes and breadth tied to the same market session, and let a desktop-triggered update stop safely without discarding already completed symbols.

## Verification

- Focused market, ingestion, and desktop tests passed, including synthetic stale-gap, quote-baseline, partial-run, and cancellation cases.
- The local database now reports all 279 current quotes with quote-based changes; ACLBSL is -0.34% from its stored previous close of NPR 872 rather than its April close.

## Related

- [[Home]]
- [[2026-10-02-market-data-coverage-gui]]
- [[Feature Change]]
