"""Boundary checks for baseline close mismatch rule."""

from __future__ import annotations

import pandas as pd

from scripts.validation.baseline_crosscheck import mismatch_share, should_exclude


def test_mismatch_share_zero_when_identical():
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    s = pd.Series([100.0, 101.0, 102.0, 103.0, 104.0], index=idx)
    assert mismatch_share(s, s) == 0.0
    assert should_exclude(0.0) is False


def test_mismatch_share_boundary_one_percent():
    idx = pd.date_range("2024-01-01", periods=4, freq="D")
    ours = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx)
    # under 1% → no mismatch; over 1% on 1/4 days → share 0.25
    theirs_under = pd.Series([100.0, 100.0 / 1.009, 100.0, 100.0], index=idx)
    assert mismatch_share(ours, theirs_under) == 0.0
    theirs_over = pd.Series([100.0, 100.0 / 1.011, 100.0, 100.0], index=idx)
    share = mismatch_share(ours, theirs_over)
    assert abs(share - 0.25) < 1e-9
    assert should_exclude(share) is True
    assert should_exclude(0.05) is False
    assert should_exclude(0.0500001) is True
