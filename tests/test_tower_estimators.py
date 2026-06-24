"""Algorithm-independent law tests for the tower point/interval estimators.

These guard the *invariants* of the views-frames tower estimators as wired into
reporting (``calculate_map_frame`` / ``calculate_hdi_frame`` and the single-cell
helpers): HDI ordering and nesting, tip-in-HDI, ``enforce_non_negative``,
determinism, the 1.3.0 no-magnitude-zeroing behaviour, NaN locality + per-cell/vectorized
consistency, and the off-grid-alpha warning. Unlike the characterization pins
(which fix exact values and must be re-baselined when the estimator changes),
these assert properties true of *any* correct tower wiring — so they catch a
regression in the reporting seam even when the numbers legitimately move.
"""

from __future__ import annotations

import logging

import numpy as np
import pytest
from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex

from views_reporting.statistics import (
    calculate_hdi_frame,
    calculate_map_frame,
    calculate_single_hdi,
    compute_single_map,
)

_T = "pred_ged_sb"


def _frame(values, level=SpatialLevel.CM) -> PredictionFrame:
    arr = np.asarray(values, dtype=np.float32)
    n = arr.shape[0]
    index = SpatioTemporalIndex(
        time=np.zeros(n, dtype=np.int64),
        unit=np.arange(n, dtype=np.int64),
        level=level,
    )
    return PredictionFrame(arr, index)


def _active_frame(seed=0, n_rows=12, n_samples=400) -> PredictionFrame:
    """Right-skewed, zero-inflated, clearly-active rows (max well above the cutoff)."""
    rng = np.random.default_rng(seed)
    vals = rng.lognormal(1.0, 0.8, (n_rows, n_samples)).astype(np.float32)
    vals[rng.random((n_rows, n_samples)) < 0.2] = 0.0
    return _frame(vals)


def test_hdi_lower_le_upper():
    hdi = calculate_hdi_frame(_active_frame(), _T, alpha=0.9)
    assert (hdi[f"{_T}_hdi_lower"] <= hdi[f"{_T}_hdi_upper"]).all()


def test_hdi_nested_across_masses():
    f = _active_frame(seed=1)
    h = {a: calculate_hdi_frame(f, _T, alpha=a) for a in (0.5, 0.9, 0.99)}
    # wider mass => wider interval: lower non-increasing, upper non-decreasing.
    assert (h[0.5][f"{_T}_hdi_lower"] >= h[0.9][f"{_T}_hdi_lower"] - 1e-6).all()
    assert (h[0.9][f"{_T}_hdi_lower"] >= h[0.99][f"{_T}_hdi_lower"] - 1e-6).all()
    assert (h[0.5][f"{_T}_hdi_upper"] <= h[0.9][f"{_T}_hdi_upper"] + 1e-6).all()
    assert (h[0.9][f"{_T}_hdi_upper"] <= h[0.99][f"{_T}_hdi_upper"] + 1e-6).all()


def test_tip_inside_hdi():
    f = _active_frame(seed=2)
    tip = calculate_map_frame(f, _T)[f"{_T}_map"].to_numpy()
    hdi = calculate_hdi_frame(f, _T, alpha=0.9)
    assert (tip >= hdi[f"{_T}_hdi_lower"].to_numpy() - 1e-6).all()
    assert (tip <= hdi[f"{_T}_hdi_upper"].to_numpy() + 1e-6).all()


def test_enforce_non_negative_clamps():
    # 70% mass near -5, 30% near +10: max > 1 (active, not zero-cutoff), but the
    # 0.5-mass floor sits on the negative cluster, so the raw tip is negative and
    # must be clamped to 0 by enforce_non_negative.
    rng = np.random.default_rng(3)
    pick = rng.random((4, 400)) < 0.7
    vals = np.where(
        pick, rng.normal(-5.0, 0.5, (4, 400)), rng.normal(10.0, 0.5, (4, 400))
    ).astype(np.float32)
    f = _frame(vals)
    raw = calculate_map_frame(f, _T)[f"{_T}_map"]
    clamped = calculate_map_frame(f, _T, enforce_non_negative=True)[f"{_T}_map"]
    assert (raw < 0).any(), "fixture should produce a negative raw tip to clamp"
    assert (clamped >= 0).all()


def test_determinism():
    f = _active_frame(seed=4)
    np.testing.assert_array_equal(
        calculate_map_frame(f, _T)[f"{_T}_map"].to_numpy(),
        calculate_map_frame(f, _T)[f"{_T}_map"].to_numpy(),
    )
    np.testing.assert_array_equal(
        calculate_hdi_frame(f, _T, alpha=0.9).to_numpy(),
        calculate_hdi_frame(f, _T, alpha=0.9).to_numpy(),
    )


def test_subunit_rows_not_zeroed():
    # views-frames 1.3.0 (ADR-019 amended): the tower is distribution-agnostic —
    # sub-1 rows are NO LONGER forced to 0 (the old magnitude-based zero cutoff is
    # off by default). An all-0.5 row keeps its value end to end.
    f = _frame(np.full((1, 50), 0.5, dtype=np.float32))
    assert calculate_map_frame(f, _T)[f"{_T}_map"].iloc[0] == pytest.approx(0.5, abs=1e-6)
    hdi = calculate_hdi_frame(f, _T, alpha=0.9)
    assert hdi[f"{_T}_hdi_lower"].iloc[0] == pytest.approx(0.5, abs=1e-6)
    assert hdi[f"{_T}_hdi_upper"].iloc[0] == pytest.approx(0.5, abs=1e-6)


def test_nan_row_local_and_consistent():
    # finite rows + one all-NaN row: the NaN row -> nan; the finite rows equal the
    # all-finite computation (the per-cell fallback uses the same tower estimator).
    rng = np.random.default_rng(5)
    good = np.abs(rng.normal(5.0, 1.0, (3, 200))).astype(np.float32)
    tip_finite = calculate_map_frame(_frame(good), _T)[f"{_T}_map"].to_numpy()

    mixed = _frame(np.vstack([good, np.full((1, 200), np.nan, dtype=np.float32)]))
    tip_mixed = calculate_map_frame(mixed, _T)[f"{_T}_map"].to_numpy()
    assert np.isnan(tip_mixed[-1])
    np.testing.assert_array_equal(tip_mixed[:3], tip_finite)


def test_single_cell_helpers_match_vectorized():
    rng = np.random.default_rng(6)
    row = np.abs(rng.normal(5.0, 1.0, 300)).astype(np.float32)
    f = _frame(row.reshape(1, -1))
    vec_tip = float(calculate_map_frame(f, _T)[f"{_T}_map"].iloc[0])
    vec_hdi = calculate_hdi_frame(f, _T, alpha=0.9)
    assert compute_single_map(row) == pytest.approx(vec_tip, abs=1e-6)
    lo, hi = calculate_single_hdi(row, 0.9)
    assert lo == pytest.approx(float(vec_hdi[f"{_T}_hdi_lower"].iloc[0]), abs=1e-6)
    assert hi == pytest.approx(float(vec_hdi[f"{_T}_hdi_upper"].iloc[0]), abs=1e-6)


def test_off_grid_alpha_warns(caplog):
    f = _active_frame(seed=7)
    with caplog.at_level(logging.WARNING):
        calculate_hdi_frame(f, _T, alpha=0.123)
    assert any("snaps to" in r.message for r in caplog.records)
