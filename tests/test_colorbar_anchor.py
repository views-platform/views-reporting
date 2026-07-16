"""Colour-scale anchoring on zero-inflated forecasts (register C-191).

The user-caught defect (2026-07-16): the colour range anchored at
``quantile(log values, [0.50, 0.95])`` — but ≥95% of PGM cell-frames are zero,
so both quantiles collapse to 0.0 and the range degenerates (cmin == cmax == 0),
silently handing the scale to the backend's auto-range. Consequences: ticks
stopped far below the bar's top (the darkest colours unlabelled) and the
"(log scale)" title invited reading original-unit labels as log units.

Contract: the saturation point anchors on the NONZERO values' log distribution,
the top of the bar is ALWAYS labelled ("≥ N" when values saturate above it),
and the legend states which part is log-scaled.

RED→GREEN history: the first commit of this file is the failing contract
(RED against the degenerate anchor); the fix commit turns it green.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

try:
    from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex

    from views_reporting.mapping.mapping import MappingModule, _log_color_scale
except ImportError:
    pytest.skip("views_frames not installed", allow_module_level=True)

TARGET = "pred_x"


def _pgm_module():
    mock_gdf = MagicMock()
    mock_gdf.columns = ["gid", "xcoord", "ycoord", "col", "row", "geometry"]
    with patch("views_reporting.mapping.mapping.gpd.read_file", return_value=mock_gdf):
        idx = SpatioTemporalIndex(
            time=np.array([528], dtype=np.int64),
            unit=np.array([1], dtype=np.int64),
            level=SpatialLevel.PGM,
        )
        return MappingModule(
            frame=PredictionFrame(np.array([[1.0]], dtype=np.float32), idx),
            level=SpatialLevel.PGM,
            target_column=TARGET,
        )


def _zero_inflated_mdf(module, n_lon=40, n_lat=20, zero_frac=0.96, vmax=500.0):
    """A realistic PGM frame: ~96% zeros, heavy tail up to ``vmax``."""
    rng = np.random.default_rng(3)
    lons = (np.arange(n_lon) * 0.5 - 10.0).astype(np.float32)
    lats = (np.arange(n_lat) * 0.5 + 0.25).astype(np.float32)
    xx, yy = np.meshgrid(lons, lats)
    n = xx.size
    vals = rng.lognormal(1.0, 1.5, n).astype(np.float32)
    vals[rng.random(n) < zero_frac] = 0.0
    vals[0] = vmax  # guarantee a heavy hotspot above any q95 anchor
    return pd.DataFrame(
        {
            module._location_col: np.arange(1, n + 1),
            module._time_id: 528,
            TARGET: vals,
            "xcoord": xx.ravel(),
            "ycoord": yy.ravel(),
            "row": 0,
            "col": 0,
        }
    )


# ── The helper's contract (all three surfaces share it) ─────────────────────


@pytest.mark.red_team
def test_anchor_not_degenerate_on_zero_inflated_values():
    """q95-of-ALL-values collapses to 0 on ≥95%-zero data; the anchor must use
    the NONZERO distribution instead (the C-191 defect)."""
    vals = np.zeros(1000, dtype=np.float32)
    vals[:40] = np.array([1, 2, 5, 10] * 10, dtype=np.float32)
    cmax, tick_log, tick_text = _log_color_scale(vals)
    assert cmax > np.log1p(1.0) * 0.99  # not the degenerate 0.0
    ref = np.quantile(np.log1p(vals[vals > 0].astype(np.float64)), 0.90)
    assert cmax >= ref - 1e-9


@pytest.mark.green_team
def test_top_of_bar_always_labelled():
    """The final tick sits AT the saturation point; labelled '≥ N' when values
    exceed it — the darkest colours can never be an unlabelled mystery zone."""
    vals = np.zeros(1000, dtype=np.float32)
    vals[:50] = np.linspace(1, 60, 50, dtype=np.float32)
    vals[0] = 500.0  # saturates well above q95 of nonzero
    cmax, tick_log, tick_text = _log_color_scale(vals)
    assert np.isclose(tick_log[-1], cmax)
    assert tick_text[-1].startswith("≥ ")
    assert all(t < cmax for t in tick_log[:-1])  # candidates stay below the top


@pytest.mark.green_team
def test_no_saturation_means_exact_top_label():
    vals = np.zeros(200, dtype=np.float32)
    vals[:20] = np.linspace(1, 10, 20, dtype=np.float32)
    cmax, tick_log, tick_text = _log_color_scale(vals)
    assert not tick_text[-1].startswith("≥")


@pytest.mark.red_team
def test_all_zero_values_fall_back_to_floor():
    cmax, tick_log, tick_text = _log_color_scale(np.zeros(100, dtype=np.float32))
    assert cmax == pytest.approx(np.log1p(1.0))


# ── Raster wiring ────────────────────────────────────────────────────────────


@pytest.mark.red_team
def test_raster_color_range_not_degenerate_on_zero_inflated():
    """Pre-fix: cmin == cmax == 0.0 on 96%-zero data (plotly silently
    auto-ranged). Post-fix: cmin=0, cmax anchored on the nonzero tail."""
    m = _pgm_module()
    fig = m.plot_map(_zero_inflated_mdf(m), TARGET, interactive=True,
                     as_html=False, raster=True)
    ca = fig.layout.coloraxis
    assert ca.cmin == 0.0
    assert ca.cmax is not None and ca.cmax > np.log1p(1.0) * 0.99


@pytest.mark.green_team
def test_raster_colorbar_top_labelled_and_title_disambiguated():
    m = _pgm_module()
    fig = m.plot_map(_zero_inflated_mdf(m), TARGET, interactive=True,
                     as_html=False, raster=True)
    cb = fig.layout.coloraxis.colorbar
    assert np.isclose(list(cb.tickvals)[-1], fig.layout.coloraxis.cmax)
    assert list(cb.ticktext)[-1].startswith("≥")
    title = cb.title.text
    assert "original units" in title  # the expm1-misreading guard


# ── PNG wiring ───────────────────────────────────────────────────────────────


@pytest.mark.red_team
def test_png_vmax_anchored_on_nonzero_tail():
    """Pre-fix the PNG's vmax floored at log1p(1)=0.69 on zero-inflated data —
    everything above 1 fatality rendered saturated dark."""
    m = _pgm_module()
    m._coastline_cache = (np.array([0.0, np.nan]), np.array([0.0, np.nan]))
    cap = {}
    import views_reporting.mapping.mapping as mapping_mod

    real_subplots = mapping_mod.plt.subplots

    def _wrap(*a, **k):
        fig, ax = real_subplots(*a, **k)
        cap["ax"] = ax
        return fig, ax

    with patch.object(mapping_mod.plt, "subplots", side_effect=_wrap):
        m._plot_image_map(_zero_inflated_mdf(m), TARGET)
    vmin, vmax = cap["ax"].images[0].get_clim()
    assert vmin == 0.0
    assert vmax > np.log1p(2.0)  # not the degenerate log1p(1) floor
