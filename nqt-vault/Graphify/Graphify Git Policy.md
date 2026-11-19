---
title: Graphify Git Policy
tags: [graphify, git]
---

# Graphify Git Policy

## Never review on GitHub

- `graphify-out/` is in `.gitignore`.
- `.gitattributes` marks paths `export-ignore` + `linguist-generated` if force-added.
- Do not `git add -f graphify-out/`.

## Merge conflicts

If any `graphify-out/**` path conflicts (or shows conflict markers):

```bash
rm -rf graphify-out
./scripts/ops/recreate_graphify.sh
# or: graphify extract . --code-only && graphify cluster-only . --no-label
```

Do **not** hand-merge `graph.json` / `graph.html` / `GRAPH_REPORT.md`.

See [[Graphify]], [[Decision Log]] ADR-002.
