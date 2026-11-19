---
title: Validation Suite
tags: [architecture, validation]
---

# Validation Suite

```bash
python -m validation.run_all            # full C5 baseline
python -m validation.run_all --fast
```

Walk-forward, Monte Carlo, CSCV/PBO, deflated Sharpe, random baseline. Writes `reports/validation/`. Methodology: `docs/VALIDATION_METHODOLOGY.md`.

Depends on [[Signal Engine]]. Feeds judgment for [[Strategy Registry]] changes. See [[Disclaimer]].
