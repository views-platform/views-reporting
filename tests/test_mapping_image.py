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
    import geopandas as gpd
    from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex

    import views_reporting.mapping.mapping as mapping_mod
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


# ── Faithfulness / colour / overlay — figure-level contract (S5 / #193) ───────
#
# `_plot_image_map` returns a rasterized base64 string, so the figure-level contracts
# (1 cell → 1 pixel, log colour, labelled colourbar, coastline artist) can't be read
# from the return value. We capture the *real* matplotlib figure by wrapping
# `plt.subplots` — no production seam — and introspect the AxesImage it built.


def _grid_mdf(module, lons, lats, hot=None, hot_value=1000.0, drop=None, t=528):
    """A deterministic PGM lattice over the given lon/lat axes: every cell value is 1.0
    except `hot` ((xcoord, ycoord) → `hot_value`); `drop` ((xcoord, ycoord)) omits a
    cell entirely (to test no-data vs silent aggregation)."""
    rows = []
    gid = 1
    for y in lats:
        for x in lons:
            if drop is not None and (x, y) == drop:
                gid += 1
                continue
            rows.append(
                {
                    module._location_col: gid,
                    module._time_id: t,
                    TARGET: hot_value if hot == (x, y) else 1.0,
                    "xcoord": float(x),
                    "ycoord": float(y),
                    "row": 0,
                    "col": 0,
                }
            )
            gid += 1
    return pd.DataFrame(rows)


def _capture_image_fig(module, mdf):
    """Render via `_plot_image_map`, capturing the real (fig, ax) it builds + the html."""
    cap = {}
    real_subplots = mapping_mod.plt.subplots

    def _wrap(*a, **k):
        fig, ax = real_subplots(*a, **k)
        cap["fig"], cap["ax"] = fig, ax
        return fig, ax

    with patch.object(mapping_mod.plt, "subplots", side_effect=_wrap):
        cap["html"] = module._plot_image_map(mdf, TARGET)
    return cap


@pytest.mark.green_team
def test_image_is_faithful_one_cell_one_pixel():
    """A single hot cell lands at exactly its (lon, lat) lattice position — no
    aggregation (C-189), correct orientation (origin='lower', no y-flip/transpose)."""
    m = _pgm_module()
    lons = [-10.0, -9.5, -9.0, -8.5]  # 0.5°-adjacent (C-208 uniform lattice)
    lats = [0.0, 0.5, 1.0]  # sorted → hot lat 0.5 is row 1; hot lon -9.0 is column 2
    cap = _capture_image_fig(m, _grid_mdf(m, lons, lats, hot=(-9.0, 0.5)))
    arr = np.asarray(cap["ax"].images[0].get_array(), dtype=float)
    assert arr.shape == (len(lats), len(lons))
    assert np.unravel_index(np.nanargmax(arr), arr.shape) == (1, 2)


@pytest.mark.red_team
def test_omitted_cell_is_no_data_not_aggregated():
    """A missing cell stays NaN (no-data) — it is NOT back-filled from neighbours, so
    omission reads as absence, not as a silently aggregated value (C-190)."""
    m = _pgm_module()
    lons = [-10.0, -9.5, -9.0, -8.5]  # 0.5°-adjacent (C-208 uniform lattice)
    lats = [0.0, 0.5, 1.0]
    cap = _capture_image_fig(m, _grid_mdf(m, lons, lats, drop=(-8.5, 1.0)))
    arr = np.asarray(cap["ax"].images[0].get_array(), dtype=float)
    # lon -8.5 → col 3, lat 1.0 → row 2
    assert np.isnan(arr[2, 3])
    assert np.isfinite(arr).sum() == len(lons) * len(lats) - 1  # exactly one hole


@pytest.mark.green_team
def test_image_colour_is_log_scaled_with_labelled_colorbar():
    """Colour is log-compressed (C-191): the array carries log1p(value), the cmap is
    OrRd from 0, and a colourbar labelled '<target> (log scale)' is present."""
    m = _pgm_module()
    lons = [-10.0, -9.5, -9.0, -8.5]  # 0.5°-adjacent (C-208 uniform lattice)
    lats = [0.0, 0.5, 1.0]
    cap = _capture_image_fig(m, _grid_mdf(m, lons, lats, hot=(-9.0, 0.5), hot_value=1000.0))
    im = cap["ax"].images[0]
    assert im.get_cmap().name == "OrRd"
    vmin, _ = im.get_clim()
    assert vmin == 0.0
    arr = np.asarray(im.get_array(), dtype=float)
    # the hot 1000 is stored log-compressed, not raw
    assert abs(np.nanmax(arr) - np.log1p(1000.0)) < 1e-3
    cbar_axes = [a for a in cap["fig"].axes if a is not cap["ax"]]
    assert cbar_axes, "no colourbar axis"
    assert cbar_axes[0].get_ylabel() == f"{TARGET} (log scale)"


@pytest.mark.green_team
def test_png_draws_coastline_artist():
    """The PNG carries a real coastline line artist (not just bounded bytes), drawn as
    a single NaN-separated polyline."""
    m = _pgm_module()
    cap = _capture_image_fig(m, _lattice_mdf(m, 20, 10))
    assert cap["ax"].lines, "no coastline artist on the PNG axes"
    xd = np.asarray(cap["ax"].lines[0].get_xdata(), dtype=float)
    assert np.isnan(xd).any()  # one polyline, NaN-separated segments


@pytest.mark.red_team
def test_overlay_does_not_load_priogrid_shapefile():
    """The coastline overlay reads the ~700 KB Natural-Earth country layer, never the
    56 MB PRIO-GRID cell shapefile (C-23)."""
    m = _pgm_module()  # built with gpd.read_file mocked; cache still empty
    real_read = gpd.read_file
    paths: list = []

    def _spy(path, *a, **k):
        paths.append(str(path))
        return real_read(path, *a, **k)

    with patch.object(mapping_mod.gpd, "read_file", side_effect=_spy):
        m._plot_image_map(_lattice_mdf(m, 10, 10), TARGET)
    assert paths, "overlay read no shapefile"
    assert all("priogrid" not in p for p in paths)
    assert any("ne_110m" in p for p in paths)


@pytest.mark.green_team
def test_png_has_no_per_cell_hover():
    """Deliberate tradeoff: the PNG is a static <img> with NO per-cell value tooltip —
    that is why the interactive heatmap stays primary wherever it fits (epic #188)."""
    m = _pgm_module()
    html = m._plot_image_map(_lattice_mdf(m, 10, 10), TARGET).lower()
    assert html.startswith("<img ")
    assert "plotly" not in html
    assert "hovertemplate" not in html
