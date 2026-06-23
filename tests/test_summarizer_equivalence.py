"""S2 equivalence oracle — the views-frames migration safety net (epic #137).

Asserts that views-reporting's hand-rolled posterior statistics agree with the
``views_frames_summarize`` package on the *same* samples, so the S3 swap is provably
behaviour-preserving:

- **HDI is bit-exact** — both use the empirical shortest-interval on sorted samples,
  so the bounds match exactly.
- **MAP matches on peaked posteriors** — both use the histogram density-peak. It can
  diverge on *near-uniform* posteriors where the mode is ill-defined (register C-35,
  demonstrated in the determination spike); the oracle therefore asserts MAP equivalence
  on a deliberately **peaked, well-sampled** fixture, not on diffuse ones.

This must stay green against the *current* hand-rolled code (the baseline) and remain
green after S3 routes the public functions through the summarizers — where it then also
guards the wrapper/reassembly (index alignment, transpose).
"""

import numpy as np
import pandas as pd
import pytest

from tests.conftest import build_cm_forecast_df, cm_frame_from_df

pytest.importorskip("views_frames")
vfs = pytest.importorskip("views_frames_summarize")
handlers = pytest.importorskip("views_pipeline_core.data.handlers")

from views_reporting.statistics import (  # noqa: E402
    calculate_hdi,
    calculate_map,
    calculate_single_hdi,
    compute_single_map,
)

CMDataset = handlers.CMDataset


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


def test_hdi_bit_exact_vs_summarizer():
    """calculate_hdi == views_frames_summarize.hdi (exact)."""
    df = build_cm_forecast_df(n_months=4, n_countries=5, n_samples=300, seed=42)
    months = df.index.get_level_values("month_id").unique().tolist()
    countries = df.index.get_level_values("country_id").unique().tolist()

    hdi_a = calculate_hdi(CMDataset(source=df), alpha=0.9, features=["pred_ged_sb"])
    hdi_b = vfs.hdi(cm_frame_from_df(df, "ged_sb"), mass=0.9)

    lo_a = _vec(hdi_a, "pred_ged_sb_hdi_lower", months, countries)
    hi_a = _vec(hdi_a, "pred_ged_sb_hdi_upper", months, countries)
    np.testing.assert_array_equal(lo_a, hdi_b[:, 0])
    np.testing.assert_array_equal(hi_a, hdi_b[:, 1])


def test_map_matches_on_peaked_posteriors():
    """calculate_map ≈ views_frames_summarize.map_estimate on a peaked posterior."""
    df = _peaked_cm_df()
    months = df.index.get_level_values("month_id").unique().tolist()
    countries = df.index.get_level_values("country_id").unique().tolist()

    map_a = calculate_map(CMDataset(source=df), features=["pred_ged_sb"], alpha=0.9)
    map_b = vfs.map_estimate(cm_frame_from_df(df, "ged_sb")).values[:, 0]

    a = _vec(map_a, "pred_ged_sb_map", months, countries)
    # Same histogram-MAP algorithm; only float32-vs-float64 bin-edge rounding can
    # differ, bounded well under one bin width on a peaked, well-sampled posterior.
    np.testing.assert_allclose(a, map_b, atol=0.15)


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
