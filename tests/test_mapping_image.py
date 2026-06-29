"""PGM PNG/image render strategy — the scale-flat globe path (epic #188, S2 / #190).

`_plot_image_map` renders the lattice as a base64 PNG: payload is `O(figure pixels)`,
independent of cell-count — so the full global grid fits the offline byte budget where
the heatmap (dense JSON frames) cannot. Synthetic lattice only (no shapefile/VIEWSER).
"""

import base64
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

try:
    from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex

    from views_reporting.mapping.mapping import MappingModule
except ImportError:
    pytest.skip("views_frames / geopandas not installed", allow_module_level=True)

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


def _lattice_mdf(module, n_lon, n_lat, times=(528,)):
    lons = (np.arange(n_lon) * 0.5 - 179.75).astype(np.float32)
    lats = (np.arange(n_lat) * 0.5 - 89.75).astype(np.float32)
    xx, yy = np.meshgrid(lons, lats)
    x, y = xx.ravel(), yy.ravel()
    n = x.size
    gid = np.arange(1, n + 1)
    rng = np.random.default_rng(0)
    parts = [
        pd.DataFrame(
            {
                module._location_col: gid,
                module._time_id: t,
                TARGET: rng.lognormal(0.0, 1.0, n).astype(np.float32),
                "xcoord": x,
                "ycoord": y,
                "row": 0,
                "col": 0,
            }
        )
        for t in times
    ]
    return pd.concat(parts, ignore_index=True)


def _png_bytes(html: str) -> bytes:
    assert html.startswith('<img src="data:image/png;base64,'), "not a base64 PNG <img>"
    b64 = html.split("base64,", 1)[1].split('"', 1)[0]
    return base64.b64decode(b64)


@pytest.mark.green_team
def test_image_render_returns_self_contained_png():
    m = _pgm_module()
    html = m._plot_image_map(_lattice_mdf(m, 40, 20), TARGET)
    png = _png_bytes(html)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic — a real bitmap
    assert "data:image/png;base64," in html  # inlined, offline (C-28)


@pytest.mark.green_team
def test_image_payload_is_scale_flat():
    """PNG bytes track the figure resolution, NOT the cell count — an ~80× bigger grid
    stays the same order of magnitude (the heatmap would grow linearly in JSON)."""
    m = _pgm_module()
    small = len(m._plot_image_map(_lattice_mdf(m, 40, 20), TARGET))       # 800 cells
    big = len(m._plot_image_map(_lattice_mdf(m, 360, 180), TARGET))       # 64,800 cells
    assert big < 2_000_000, f"PNG not bounded: {big}"
    assert big < small * 10, "PNG grew ~linearly with cells — not scale-flat"


@pytest.mark.slow
@pytest.mark.green_team
def test_full_globe_png_is_bounded():
    """The full-globe (720×360 = 259,200-cell) PNG fits the budget — the case the
    heatmap can't carry at many origins (epic #188 canary, #189)."""
    m = _pgm_module()
    html = m._plot_image_map(_lattice_mdf(m, 720, 360), TARGET)
    assert len(_png_bytes(html)) < 2_000_000  # vs ~12.7 MB heatmap / ~85 MB choropleth


@pytest.mark.red_team
def test_image_requires_xcoord_ycoord():
    m = _pgm_module()
    mdf = _lattice_mdf(m, 10, 10).drop(columns=["xcoord", "ycoord"])
    with pytest.raises(ValueError, match="xcoord"):
        m._plot_image_map(mdf, TARGET)


# ── Coastline/border overlay (S3 / #191, register C-205) ─────────────────────


@pytest.mark.green_team
def test_coastline_xy_derived_lazily_and_cached():
    """A lon/lat border polyline from the committed ne_110m country shapefile (not the
    56 MB PRIO-GRID one), with NaN segment separators, built once + cached."""
    m = _pgm_module()
    cx, cy = m._coastline_xy()
    assert cx.shape == cy.shape and cx.size > 100  # real coastline geometry loaded
    assert np.isnan(cx).any()  # NaN separators between border segments
    assert m._coastline_xy() is m._coastline_cache  # cached (built once)


@pytest.mark.green_team
def test_heatmap_carries_coastline_overlay():
    """The PGM raster heatmap gets a static 'borders' line overlay (trace 1); the
    heatmap stays trace 0 so the animation frames still target it."""
    m = _pgm_module()
    fig = m.plot_map(_lattice_mdf(m, 40, 20), TARGET, interactive=True,
                     as_html=False, raster=True)
    assert fig.data[0].type == "heatmap"
    assert any(getattr(t, "name", None) == "borders" for t in fig.data)


@pytest.mark.green_team
def test_png_with_coastline_stays_bounded():
    """The coastline overlay on the PNG adds only kilobytes — still well within budget."""
    m = _pgm_module()
    html = m._plot_image_map(_lattice_mdf(m, 80, 40), TARGET)
    assert len(_png_bytes(html)) < 2_000_000
