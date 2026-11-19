---
name: graphify-conflicts
description: >-
  Resolve graphify artifact merge conflicts by deleting graphify-out and
  recreating the graph. Use when graphify-out conflicts, PR review shows
  graphify files, or graph.json/graph.html/GRAPH_REPORT.md are dirty in git.
---

# Graphify conflict recreate

## Rule

Never hand-merge graphify outputs. Delete and regenerate.

```bash
rm -rf graphify-out nqt-vault/Graphify/export
./scripts/ops/recreate_graphify.sh
```

Confirm `graphify-out/` stays untracked (`git status` / `.gitignore`). Do not `git add -f` these paths. They must not appear in GitHub review.

Related always-on rule: `.cursor/rules/graphify.mdc`.
