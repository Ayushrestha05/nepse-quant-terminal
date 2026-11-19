---
title: Native Floor Engine
tags: [architecture, native, rust]
---

# Native Floor Engine

Optional Rust module `native/nqt_floor` for broker-panel metrics (~5× Python). Build:

```bash
pip install maturin && maturin develop --release -m native/nqt_floor/Cargo.toml
```

Force Python: `NQT_FLOOR_ENGINE=python`.

Python fallback: `apps/tui/io/floor_metrics.py`. Used by [[Tab Signals]] broker panels when connected via [[Website Connect]].

Related: [[Architecture Overview]], [[TUI Dashboard]].
