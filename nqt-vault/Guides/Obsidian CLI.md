---
title: Obsidian CLI
tags: [guide, vault]
---

# Obsidian CLI

Manage this vault with the Obsidian CLI while the app is running (`cli: true` in Obsidian config):

```bash
obsidian vault=nqt-vault files
obsidian vault=nqt-vault create path="Components/Example.md" content="# Example\n\nSee [[TUI Dashboard]]."
obsidian vault=nqt-vault search query="paper"
obsidian vault=nqt-vault unresolved
obsidian vault=nqt-vault open file="00 - Index"
```

Related: [[Vault Conventions]] · [[00 - Index]] · [[Change Log]].
