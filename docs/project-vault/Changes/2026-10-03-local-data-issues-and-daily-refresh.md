---
title: Shared local data, daily refresh, and persistent issues
date: 2026-10-03
tags:
  - change
  - market-data
  - paper-trading
---

# Shared local data, daily refresh, and persistent issues

## What changed

- Added a process-wide SQLite price-history snapshot shared by Signals and every paper account. Successful ingestion refreshes changed symbols in that snapshot.
- Added market-hours quote refresh scheduling and completed-session bar catch-up. Automatic catch-up is limited to gaps of 14 days; older gaps are labelled for manual history updates.
- Added a SQLite-backed Issues page with retry cooldowns, issue categories, attempts, and an event history. Legacy pending vendor resyncs are visible there. HTTP 429 responses stop the provider batch and defer the remaining symbols.
- Added paper-buy guards for a stale NEPSE benchmark, stale candidate bars, unresolved history issues, and quotes older than 120 seconds.
- Added regression coverage for issue state, 429 cooldown and deferral, cancellation and retry resolution, shared cache refresh, session scheduling, and stale paper buys.

## Why

Accounts were loading duplicate full price histories, daily bars could remain stale after an app started, and failed ingestion work did not have one persistent place to inspect or retry. Paper orders also needed explicit safeguards when local bars or quotes were out of date.

## Purpose

Keep quick app views on a shared local snapshot, refresh daily data without mixing it with intraday quotes, and make incomplete or rate-limited data visible and recoverable while blocking buys that lack reliable completed-session data.

## Verification

- Focused unit tests cover shared price loading and refresh, daily session boundaries, 14-day scheduler classification, issue event history, `Retry-After`, provider batch stopping, partial ingestion, cancellation, successful issue resolution, and stale benchmark/candidate/quote guards.
- Linux local-data measurement: the 460,640-row database snapshot loaded in 0.671 seconds, a cached lookup took 0.000067 seconds, and process peak RSS was 306.9 MiB for that Python run.
- Full unit suite and Linux GUI smoke check are run before merge.
- See [[Home|Change log]] for related features and [[Start Here|Vault index]] for project documentation.
