---
title: "Linux launcher and publishing workflow"
date: 2026-10-03
tags:
  - change
  - linux
  - workflow
---

# Linux launcher and publishing workflow

## What changed

- Added a Linux launcher that chooses supported Python, reuses the app bootstrap, and installs an idempotent per-user application-menu entry.
- Documented Linux launch setup with shell-quoted commands for its spaced filename, and recorded the authorized push policy in the repository workflow.
- Set the Git origin to the user's repository. Kept the configured database release as a separate data source.

## Why

Linux lacked a direct launch script and application-menu entry, and the repository workflow did not capture the user's ongoing push preference.

## Purpose

Launch the dashboard from Linux and publish finished, checked changes to the requested repository.

## Verification

- Launcher and desktop focused suites passed as part of the 38-test feature check; the full unit suite passed (388 tests).
- `bash -n` and `desktop-file-validate` passed on both the actual installed per-user entry and a path containing spaces. Obsidian links in changed documentation were checked.
- The requested repository's `main` matched the old repository's shared base before these changes. The existing database-release URL remains on the original data repository.

## Related

- [[Home]]
- [[../../EASY_LAUNCH|Easy Launch]]
- [[Feature Change]]
