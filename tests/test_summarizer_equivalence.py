"""Tower equivalence oracle — the views-frames wrapper safety net (epic #137).

Asserts that views-reporting's public posterior statistics agree **exactly** with the
``views_frames_summarize`` **tower** estimators on the *same* samples — the estimators
the public functions now route through after the tower swap (``tower_point`` /
``hdi_tower``; reporting register C-35 / ADR-019). It is no longer a
behaviour-*preservation* gate (the swap deliberately changed the numbers vs the
old frozen MAP/HDI); it guards the
reporting-owned **wrapper/reassembly** (index alignment, transpose, float64 cast,
per-cell NaN routing) against the leaf.

- **Point estimate is bit-exact** — ``calculate_map_frame`` reads ``tower_point``
  directly (no histogram binning), so the values match exactly (modulo the
  float32→float64 cast).
- **HDI is bit-exact** — ``calculate_hdi_frame`` reads the single-mass ``hdi_tower`` floor.

The algorithm-independent invariants (nesting, tip∈HDI, non-negativity, determinism)
are guarded separately by ``tests/test_tower_estimators.py``.
"""

import numpy as np
import pandas as pd
import pytest

from tests.conftest import build_cm_forecast_df, cm_frame_from_df

pytest.importorskip("views_frames")
vfs = pytest.importorskip("views_frames_summarize")

from views_reporting.statistics import (  # noqa: E402
    calculate_hdi_frame,
    calculate_map_frame,
    calculate_single_hdi,
    compute_single_map,
)


def _vec(df_result, col, months, countries):
    """Flatten a (month, country) MultiIndex result column into a time-major vector."""
    return np.array(
        [df_result.loc[(m, c), col] for m in months for c in countries],
        dtype=np.float32,
    )


def _peaked_cm_df(n_months=4, n_countries=5, n_samples=2000, seed=7):
    """A peaked, well-sampled CM forecast df so the histogram MAP is unambiguous."""
    rng = np.random.RandomState(seed)
    months = list(range(528, 528 + n_months))
    countries = list(range(1, n_countries + 1))
    idx = pd.MultiIndex.from_product(
        [months, countries], names=["month_id", "country_id"]
    )
    data = {
        "pred_ged_sb": [
            np.abs(rng.normal(5.0, 0.5, n_samples)).astype(np.float32)
            for _ in range(len(idx))
        ]
    }
    return pd.DataFrame(data, index=idx)


def test_hdi_bit_exact_vs_tower():
    """calculate_hdi == views_frames_summarize.hdi_tower single-mass floor (exact)."""
    df = build_cm_forecast_df(n_months=4, n_countries=5, n_samples=300, seed=42)
    months = df.index.get_level_values("month_id").unique().tolist()
    countries = df.index.get_level_values("country_id").unique().tolist()

    hdi_a = calculate_hdi_frame(cm_frame_from_df(df, "ged_sb"), "pred_ged_sb", alpha=0.9)
    hdi_b = vfs.hdi_tower(cm_frame_from_df(df, "ged_sb"), masses=(0.9,))[:, 0, :]

    lo_a = _vec(hdi_a, "pred_ged_sb_hdi_lower", months, countries)
    hi_a = _vec(hdi_a, "pred_ged_sb_hdi_upper", months, countries)
    np.testing.assert_array_equal(lo_a, hdi_b[:, 0])
    np.testing.assert_array_equal(hi_a, hdi_b[:, 1])


def test_point_bit_exact_vs_tower():
    """calculate_map == views_frames_summarize.tower_point (exact; no binning)."""
    df = _peaked_cm_df()
    months = df.index.get_level_values("month_id").unique().tolist()
    countries = df.index.get_level_values("country_id").unique().tolist()

    map_a = calculate_map_frame(cm_frame_from_df(df, "ged_sb"), "pred_ged_sb")
    map_b = vfs.tower_point(cm_frame_from_df(df, "ged_sb")).values[:, 0]

    a = _vec(map_a, "pred_ged_sb_map", months, countries)
    # tower_point is unbinned and deterministic; the only transform is the
    # reporting-owned float32 -> float64 cast, so the values match exactly.
    np.testing.assert_array_equal(a, map_b.astype(np.float64))


def test_single_cell_helpers_strip_partial_nan():
    """The public single-cell helpers preserve the legacy per-cell NaN-strip:
    a cell with *some* NaN yields a finite MAP/HDI from the finite samples (not a
    crash or a malformed finite-lower/NaN-upper HDI), and an all-NaN cell yields
    NaN. (The CMDataset tensor path itself rejects NaN upstream, so this guards the
    directly-callable helpers — and the frame path that arrives in S4.)"""
    rng = np.random.RandomState(3)
    partial = np.abs(rng.normal(5.0, 0.5, 80)).astype(np.float32)
    partial[:20] = np.nan

    assert np.isfinite(compute_single_map(partial))
    lo, hi = calculate_single_hdi(partial, 0.9)
    assert np.isfinite(lo) and np.isfinite(hi)

    all_nan = np.full(50, np.nan, dtype=np.float32)
    assert np.isnan(compute_single_map(all_nan))
    assert all(np.isnan(x) for x in calculate_single_hdi(all_nan, 0.9))
