"""Globe-expansion canary (epic #188, S1 / #189): characterize the raster heatmap's
cost at global PRIO-GRID dimension and pin where it must escalate to the PNG fallback.

A single global frame is bounded (the heatmap stays viable, keeps hover); a global
grid × several rolling origins exceeds the default ``max_raster_cell_frames`` budget
and fails loud — the crossover the PNG path (S2-S4) targets. Synthetic full-lattice
only — no 56 MB shapefile, no VIEWSER (avoids the C-46 fixture trap).
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

try:
    from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex

    from views_reporting.config import get_config
    from views_reporting.mapping.mapping import MappingModule
except ImportError:
    pytest.skip("views_frames / geopandas not installed", allow_module_level=True)

TARGET = "pred_x"
# Full-resolution global 0.5° lattice ≈ 720 lon × 360 lat = 259,200 cells.
_N_LON, _N_LAT = 720, 360


def _pgm_module():
    """A PGM MappingModule with the shapefile read mocked (the raster path needs no
    geometry — only the per-cell xcoord/ycoord in the mapping dataframe)."""
    mock_gdf = MagicMock()
    mock_gdf.columns = ["gid", "xcoord", "ycoord", "col", "row", "geometry"]
    with patch("views_reporting.mapping.mapping.gpd.read_file", return_value=mock_gdf):
        idx = SpatioTemporalIndex(
            time=np.array([528], dtype=np.int64),
            unit=np.array([1], dtype=np.int64),
            level=SpatialLevel.PGM,
        )
        frame = PredictionFrame(np.array([[1.0]], dtype=np.float32), idx)
        return MappingModule(frame=frame, level=SpatialLevel.PGM, target_column=TARGET)


def _global_lattice_mdf(module, n_lon=_N_LON, n_lat=_N_LAT, times=(528,)):
    """A synthetic global PGM mapping dataframe: a regular 0.5° lon/lat lattice of
    ``n_lon × n_lat`` cells, replicated across ``times`` rolling origins."""
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


@pytest.mark.slow
@pytest.mark.green_team
def test_single_origin_global_heatmap_is_bounded():
    """A full-globe (~259k-cell) SINGLE-origin heatmap renders within budget — so
    single-origin global maps stay on the hover-capable heatmap; no PNG needed there.
    (The cost driver is animation *frames*, not the grid itself — one frame is fine.)"""
    m = _pgm_module()
    mdf = _global_lattice_mdf(m, times=(528,))
    assert len(mdf) == _N_LON * _N_LAT  # ~259,200 cell-frames, single origin
    html = m.plot_map(
        mdf,
        TARGET,
        interactive=True,
        as_html=True,
        raster=True,
        max_raster_cell_frames=get_config().max_raster_cell_frames,
    )
    # one dense frame, no animation multiplier → bounded (vs the multi-GB choropleth).
    # Canary datapoint for S4's heatmap→PNG threshold: bytes/cell ≈ len(html)/259k.
    assert len(html) < 40_000_000, f"single-origin global heatmap too large: {len(html)}"


@pytest.mark.slow
@pytest.mark.red_team
def test_multiorigin_global_heatmap_refused_by_default_budget():
    """A full-globe grid × several rolling origins exceeds the default
    ``max_raster_cell_frames`` (1,000,000) → fail-loud. This is the crossover where the
    PNG image fallback (epic #188, S2-S4) must take over — the heatmap can't carry it."""
    m = _pgm_module()
    n_origins = 4  # 259,200 × 4 ≈ 1.04M cell-frames > 1,000,000 default
    mdf = _global_lattice_mdf(m, times=tuple(528 + i for i in range(n_origins)))
    assert len(mdf) > get_config().max_raster_cell_frames
    with pytest.raises(ValueError, match="max_raster_cell_frames"):
        m.plot_map(
            mdf,
            TARGET,
            interactive=True,
            as_html=True,
            raster=True,
            max_raster_cell_frames=get_config().max_raster_cell_frames,
        )
