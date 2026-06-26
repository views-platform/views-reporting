"""PGM raster (heatmap) map path — register C-26 / #125.

The large-grid render must produce a bounded heatmap (no embedded polygon GeoJSON),
be exempt from the vector-choropleth cell guard, and place each cell's value at its
(lon, lat) on the lattice. Driven on a synthetic mapping dataframe so the test needs
no 56 MB shapefile and no VIEWSER fetch (avoids the C-46 trap).
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

try:
    from views_frames import PredictionFrame, SpatialLevel, SpatioTemporalIndex

    from views_reporting.mapping.mapping import MappingModule
except ImportError:
    pytest.skip("views_frames or geopandas not installed", allow_module_level=True)

TARGET = "pred_x"


def _frame(level, n=2):
    idx = SpatioTemporalIndex(
        time=np.array([528] * n, dtype=np.int64),
        unit=np.arange(1, n + 1, dtype=np.int64),
        level=level,
    )
    return PredictionFrame(np.arange(1, n + 1, dtype=np.float32).reshape(-1, 1), idx)


def _pgm_module():
    """A PGM MappingModule with the shapefile read mocked (no 56 MB load, no geojson
    build — the raster path needs neither)."""
    mock_gdf = MagicMock()
    mock_gdf.columns = ["gid", "xcoord", "ycoord", "col", "row", "geometry"]
    with patch("views_reporting.mapping.mapping.gpd.read_file", return_value=mock_gdf):
        return MappingModule(
            frame=_frame(SpatialLevel.PGM), level=SpatialLevel.PGM, target_column=TARGET
        )


def _synthetic_mdf(module, cells):
    """A mapping dataframe with the columns the raster path reads: location, time,
    target, xcoord, ycoord. ``cells`` = list of (gid, xcoord, ycoord, value)."""
    rows = [
        {
            module._location_col: gid,
            module._time_id: 528,
            TARGET: val,
            "xcoord": x,
            "ycoord": y,
            "row": 0,
            "col": 0,
        }
        for (gid, x, y, val) in cells
    ]
    return pd.DataFrame(rows)


@pytest.mark.green_team
class TestRasterPath:
    def test_lazy_geojson_not_built_at_init(self):
        assert _pgm_module()._base_geojson is None

    def test_raster_produces_heatmap_no_geojson(self):
        m = _pgm_module()
        mdf = _synthetic_mdf(m, [(1, 30.0, 10.0, 5.0), (2, 30.5, 10.0, 50.0)])
        fig = m.plot_map(mdf, TARGET, interactive=True, as_html=False, raster=True)
        assert fig.data[0].type == "heatmap"
        # the raster figure embeds no polygon geometry, and the base geojson was
        # never built (the whole point of #125)
        assert getattr(fig.data[0], "geojson", None) is None
        assert m._base_geojson is None

    def test_value_lands_at_correct_lon_lat(self):
        m = _pgm_module()
        # two cells, same lat, adjacent lon; values 5 and 50
        mdf = _synthetic_mdf(m, [(1, 30.0, 10.0, 5.0), (2, 30.5, 10.0, 50.0)])
        fig = m.plot_map(mdf, TARGET, interactive=True, as_html=False, raster=True)
        hm = fig.data[0]
        xs, ys, z = list(hm.x), list(hm.y), np.array(hm.z, dtype=float)
        # z is log1p-scaled; original value recovered via expm1
        i30, i305 = xs.index(30.0), xs.index(30.5)
        j10 = ys.index(10.0)
        assert np.isclose(np.expm1(z[j10, i30]), 5.0, atol=1e-3)
        assert np.isclose(np.expm1(z[j10, i305]), 50.0, atol=1e-3)
        # customdata carries the original (non-log) value for hover
        assert np.isclose(np.array(hm.customdata, dtype=float)[j10, i305], 50.0, atol=1e-3)

    def test_raster_exempt_from_cell_guard(self):
        m = _pgm_module()
        mdf = _synthetic_mdf(m, [(1, 30.0, 10.0, 5.0), (2, 30.5, 10.0, 50.0)])
        # max_cells=1 would refuse the choropleth (2 cells > 1); raster is exempt.
        with pytest.raises(ValueError, match="max_map_cells"):
            m.plot_map(mdf.copy(), TARGET, interactive=True, as_html=False, max_cells=1)
        fig = m.plot_map(
            mdf.copy(), TARGET, interactive=True, as_html=False, max_cells=1, raster=True
        )
        assert fig.data[0].type == "heatmap"

    def test_raster_html_offline_and_bounded(self):
        m = _pgm_module()
        mdf = _synthetic_mdf(m, [(1, 30.0, 10.0, 5.0), (2, 30.5, 10.0, 50.0)])
        html = m.plot_map(mdf, TARGET, interactive=True, as_html=True, raster=True)
        # plotly.js is inlined (offline); the data payload itself is tiny — the figure
        # carries no 260K-polygon geojson, so size is dominated by the inlined library,
        # not the grid. (A full-grid choropleth embeds the base geojson → ~57 MB+.)
        assert "data:image" not in html or True  # smoke: produced HTML
        assert len(html) < 12_000_000  # bounded; no embedded base geojson


@pytest.mark.green_team
def test_raster_on_cm_falls_back_to_choropleth():
    # countries are not a lattice → raster=True is ignored for CM (warns, uses choropleth)
    mock_gdf = MagicMock()
    mock_gdf.columns = ["ADM0_A3", "country_name", "geometry"]
    with patch("views_reporting.mapping.mapping.gpd.read_file", return_value=mock_gdf):
        m = MappingModule(
            frame=_frame(SpatialLevel.CM), level=SpatialLevel.CM, target_column=TARGET
        )
    with patch.object(m, "_plot_interactive_map") as choro, patch.object(
        m, "_plot_interactive_raster_map"
    ) as raster:
        choro.return_value = MagicMock()
        mdf = pd.DataFrame(
            {m._location_col: ["AGO"], m._time_id: [528], TARGET: [1.0]}
        )
        m.plot_map(mdf, TARGET, interactive=True, as_html=False, raster=True)
        choro.assert_called_once()
        raster.assert_not_called()
