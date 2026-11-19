#!/usr/bin/env bash
# Recreate local graphify artifacts. Use after merge conflicts or a stale graph.
# Artifacts are gitignored — never commit graphify-out/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if ! command -v graphify >/dev/null 2>&1; then
  echo "graphify not found. Install: uv tool install graphifyy" >&2
  exit 1
fi

echo "[recreate_graphify] removing $ROOT/graphify-out"
rm -rf graphify-out

echo "[recreate_graphify] extract (code-only)"
graphify extract . --code-only \
  --exclude 'nqt-vault/**' \
  --exclude 'graphify-out/**'

echo "[recreate_graphify] cluster (no LLM labels)"
graphify cluster-only . --no-label

echo "[recreate_graphify] done → graphify-out/{graph.json,graph.html,GRAPH_REPORT.md}"
