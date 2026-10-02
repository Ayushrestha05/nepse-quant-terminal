---
title: Project change tracking vault
date: 2026-10-02
tags:
  - change
  - workflow
---

# Project change tracking vault

## What changed

Added this Obsidian vault, a reusable feature-change note template, and repository guidance for keeping notes with local Git commits.

## Why

The project needs a durable record of what changed, why it changed, and what each change is for. Git diffs alone preserve implementation details but not this context.

## Purpose

Use [[Home]] to browse change notes. For every coherent feature, fix, or documentation change, create a note from [[Feature Change]] and commit it alongside the affected files. The Git commit remains the source for exact file history.

## Verification

- Confirmed each internal wikilink points to a note in this vault.
- Confirmed the commit policy requires focused checks and excludes unrelated working-tree files.

## Related

- [[Home]]
- [[Feature Change]]
