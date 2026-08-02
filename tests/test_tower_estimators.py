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


# ── C-186: behavioural-regime coverage ──────────────────────────────────────
# The law tests above run on the "active" regime (max >> 1). A views-frames bump
# can silently change the tower's numbers within the same CONFORMANCE_FLOOR (the
# 1.2.0->1.3.0 zero-policy flip). These exercise the regimes conflict forecasts
# actually occupy — sub-1, heavy zero-inflation, multimodal — with the regime-
# agnostic law invariants PLUS a per-regime behavioural assertion, so a tower
# behaviour flip in those regimes fails loud on the next bump (register C-186).

_LOW_MODE, _HIGH_MODE = 2.0, 20.0


def _subunit_frame(seed=10, n_rows=8, n_samples=400) -> PredictionFrame:
    """All samples in [0, 1) — the tower must not zero or inflate them."""
    rng = np.random.default_rng(seed)
    return _frame(rng.uniform(0.0, 1.0, (n_rows, n_samples)).astype(np.float32))


def _zero_inflated_frame(
    seed=11, n_rows=8, n_samples=400, zero_frac=0.85
) -> PredictionFrame:
    """>=85% structural zeros + a heavy positive tail — the point estimate should
    collapse toward 0 (the zeros dominate the 0.5-mass floor)."""
    rng = np.random.default_rng(seed)
    vals = rng.lognormal(1.5, 0.8, (n_rows, n_samples)).astype(np.float32)
    vals[rng.random((n_rows, n_samples)) < zero_frac] = 0.0
    return _frame(vals)


def _multimodal_frame(seed=12, n_rows=8, n_samples=400) -> PredictionFrame:
    """Two well-separated positive modes (~2 and ~20) — the tip must land inside a
    mode, not the empty gap between them."""
    rng = np.random.default_rng(seed)
    pick = rng.random((n_rows, n_samples)) < 0.5
    vals = np.where(
        pick,
        rng.normal(_LOW_MODE, 0.3, (n_rows, n_samples)),
        rng.normal(_HIGH_MODE, 1.0, (n_rows, n_samples)),
    ).astype(np.float32)
    return _frame(np.clip(vals, 0.0, None))


_REGIMES = {
    "subunit": _subunit_frame,
    "zero_inflated": _zero_inflated_frame,
    "multimodal": _multimodal_frame,
}


@pytest.mark.green_team
@pytest.mark.parametrize("regime", list(_REGIMES))
def test_tower_laws_hold_in_each_regime(regime):
    """The estimator invariants must hold in EVERY regime, not just the active one
    — a frames bump that breaks ordering / nesting / tip-in-HDI / determinism in a
    sub-1, zero-inflated, or multimodal regime fails loud here (C-186)."""
    f = _REGIMES[regime]()
    tip = calculate_map_frame(f, _T)[f"{_T}_map"].to_numpy()
    h = {a: calculate_hdi_frame(f, _T, alpha=a) for a in (0.5, 0.9, 0.99)}
    lo = {a: h[a][f"{_T}_hdi_lower"].to_numpy() for a in h}
    hi = {a: h[a][f"{_T}_hdi_upper"].to_numpy() for a in h}

    assert np.isfinite(tip).all()
    for a in h:
        assert np.isfinite(lo[a]).all() and np.isfinite(hi[a]).all()
    assert (lo[0.9] <= hi[0.9]).all()  # lower <= upper
    # nested: wider mass => wider interval
    assert (lo[0.5] >= lo[0.9] - 1e-6).all() and (lo[0.9] >= lo[0.99] - 1e-6).all()
    assert (hi[0.5] <= hi[0.9] + 1e-6).all() and (hi[0.9] <= hi[0.99] + 1e-6).all()
    # tip inside the 0.9 HDI
    assert (tip >= lo[0.9] - 1e-6).all() and (tip <= hi[0.9] + 1e-6).all()
    # determinism
    np.testing.assert_array_equal(
        tip, calculate_map_frame(f, _T)[f"{_T}_map"].to_numpy()
    )


@pytest.mark.green_team
def test_subunit_regime_not_zeroed():
    """Sub-1 data keeps its magnitude (the 1.3.0 fix): tips are in (0, 1) and reflect
    the ~0.5 central tendency, NOT forced to 0 (a magnitude/zero-cutoff regression)."""
    tip = calculate_map_frame(_subunit_frame(), _T)[f"{_T}_map"].to_numpy()
    assert (tip > 0.0).all() and (tip < 1.0).all()
    assert tip.mean() > 0.2, "sub-1 tips collapsed toward 0 — zero-cutoff regression?"


@pytest.mark.green_team
def test_zero_inflated_regime_collapses_to_zero():
    """When >=85% of mass sits at 0, the point estimate collapses toward 0 (the
    0.5-mass floor is on the zeros). A flip to a non-zero (e.g. mean-based) estimate
    would fail this."""
    f = _zero_inflated_frame()
    tip = calculate_map_frame(f, _T)[f"{_T}_map"].to_numpy()
    lo = calculate_hdi_frame(f, _T, alpha=0.9)[f"{_T}_hdi_lower"].to_numpy()
    assert tip == pytest.approx(np.zeros_like(tip), abs=1e-3)
    assert lo == pytest.approx(np.zeros_like(lo), abs=1e-3)


@pytest.mark.green_team
def test_multimodal_tip_lands_in_a_mode_not_the_gap():
    """The tip sits inside one of the separated modes (~2 or ~20), never in the empty
    inter-mode gap — a tower change that averaged the modes (tip in the gap) fails."""
    tip = calculate_map_frame(_multimodal_frame(), _T)[f"{_T}_map"].to_numpy()
    in_low = np.abs(tip - _LOW_MODE) <= 1.5
    in_high = np.abs(tip - _HIGH_MODE) <= 3.0
    assert (in_low | in_high).all(), f"tip landed in the inter-mode gap: {tip}"
