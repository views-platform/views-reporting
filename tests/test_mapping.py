"""
CIC coverage for MappingModule (frame path, epic #137).

Red team: input validation, type checking.
Green team: constructor dispatch, shapefile loading.
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


def _small_frame(level, n=3):
    """A tiny single-sample PredictionFrame at the given level."""
    index = SpatioTemporalIndex(
        time=np.array([528] * n, dtype=np.int64),
        unit=np.arange(1, n + 1, dtype=np.int64),
        level=level,
    )
    values = np.arange(1, n + 1, dtype=np.float32).reshape(-1, 1)
    return PredictionFrame(values, index)


# ── Red team: validation ─────────────────────────────────────────────────


@pytest.mark.red_team
class TestMappingModuleValidation:

    @patch("views_reporting.mapping.mapping.MappingModule._prepare_base_geojson")
    @patch("views_reporting.mapping.mapping.gpd.read_file")
    def test_invalid_level_raises(self, mock_read_file, _):
        mock_read_file.return_value = MagicMock(columns=["geometry"])
        with pytest.raises((ValueError, AttributeError)):
            MappingModule(
                frame=_small_frame(SpatialLevel.CM),
                level="not_a_level",
                target_column="pred_ged_sb",
            )


# ── Green team: constructor dispatch ─────────────────────────────────────


@pytest.mark.green_team
class TestMappingModuleConstructor:

    @patch("views_reporting.mapping.mapping.MappingModule._prepare_base_geojson")
    @patch("views_reporting.mapping.mapping.gpd.read_file")
    def test_pgm_loads_priogrid_shapefile(self, mock_read_file, _):
        mock_gdf = MagicMock()
        mock_gdf.columns = ["gid", "row", "col", "geometry"]
        mock_read_file.return_value = mock_gdf

        mapper = MappingModule(
            frame=_small_frame(SpatialLevel.PGM),
            level=SpatialLevel.PGM,
            target_column="pred_ged_sb",
        )
        call_path = str(mock_read_file.call_args[0][0])
        assert "priogrid" in call_path
        assert mapper._location_col == "gid"

    @patch("views_reporting.mapping.mapping.MappingModule._prepare_base_geojson")
    @patch("views_reporting.mapping.mapping.gpd.read_file")
    def test_cm_loads_country_shapefile(self, mock_read_file, _):
        mock_gdf = MagicMock()
        mock_gdf.columns = ["ADM0_A3", "geometry"]
        mock_read_file.return_value = mock_gdf

        mapper = MappingModule(
            frame=_small_frame(SpatialLevel.CM),
            level=SpatialLevel.CM,
            target_column="pred_ged_sb",
        )
        call_path = str(mock_read_file.call_args[0][0])
        assert "country" in call_path
        assert mapper._location_col == "ADM0_A3"


# ── Green team: integration with real shapefiles ─────────────────────────


@pytest.mark.green_team
@pytest.mark.slow
class TestMappingModuleIntegration:

    def test_cm_constructor_loads_real_shapefiles(self):
        mapper = MappingModule(
            frame=_small_frame(SpatialLevel.CM),
            level=SpatialLevel.CM,
            target_column="pred_ged_sb",
        )
        assert mapper._location_col == "ADM0_A3"
        # GeoJSON is now built lazily on first choropleth render (#125), not at init,
        # so the raster path can skip it entirely.
        assert mapper._base_geojson is None
        mapper._prepare_base_geojson()
        assert mapper._base_geojson["type"] == "FeatureCollection"


# ── Red team: scale guard (C-26) ─────────────────────────────────────────


def _build_pg_mapper(mock_read_file):
    """A MappingModule over a PGM frame — no real shapefile, no geojson."""
    mock_gdf = MagicMock()
    mock_gdf.columns = ["gid", "row", "col", "geometry"]
    mock_read_file.return_value = mock_gdf
    return MappingModule(
        frame=_small_frame(SpatialLevel.PGM),
        level=SpatialLevel.PGM,
        target_column="pred_ged_sb",
    )


def _mapping_df(n_rows):
    """A minimal mapping dataframe with `n_rows` renderable entries."""
    return pd.DataFrame({"pred_ged_sb": [np.array([1.0]) for _ in range(n_rows)]})


@pytest.mark.red_team
class TestMappingScaleGuard:
    """The fail-loud cell-count guard (register C-26): refuse to render an
    oversized map rather than OOM / emit a multi-GB file. `max_cells` is injected
    from ReportingConfig at the Compose boundary (ADR-016)."""

    @patch("views_reporting.mapping.mapping.MappingModule._prepare_base_geojson")
    @patch("views_reporting.mapping.mapping.gpd.read_file")
    def test_guard_raises_above_threshold(self, mock_read_file, _):
        mapper = _build_pg_mapper(mock_read_file)
        # 11 cells, limit 10 → fail loud BEFORE any trace construction.
        with pytest.raises(ValueError) as excinfo:
            mapper.plot_map(
                _mapping_df(11), "pred_ged_sb", interactive=True, max_cells=10
            )
        msg = str(excinfo.value)
        # Names the cell count, the threshold, and the override field (DoD).
        assert "11" in msg and "10" in msg and "max_map_cells" in msg

    @patch("views_reporting.mapping.mapping.MappingModule._prepare_base_geojson")
    @patch("views_reporting.mapping.mapping.gpd.read_file")
    def test_guard_fires_exactly_above_not_at_threshold(self, mock_read_file, _):
        mapper = _build_pg_mapper(mock_read_file)
        # Exactly at the limit must NOT raise (guard is strict `>`).
        with patch.object(mapper, "_plot_interactive_map", return_value="FIG"):
            out = mapper.plot_map(
                _mapping_df(10), "pred_ged_sb", interactive=True, max_cells=10
            )
        assert out == "FIG"

    @patch("views_reporting.mapping.mapping.MappingModule._prepare_base_geojson")
    @patch("views_reporting.mapping.mapping.gpd.read_file")
    def test_guard_passes_below_threshold(self, mock_read_file, _):
        mapper = _build_pg_mapper(mock_read_file)
        with patch.object(
            mapper, "_plot_interactive_map", return_value="FIG"
        ) as mock_plot:
            out = mapper.plot_map(
                _mapping_df(5), "pred_ged_sb", interactive=True, max_cells=10
            )
        assert out == "FIG"
        mock_plot.assert_called_once()  # proceeded past the guard into rendering

    @patch("views_reporting.mapping.mapping.MappingModule._prepare_base_geojson")
    @patch("views_reporting.mapping.mapping.gpd.read_file")
    def test_guard_disabled_when_max_cells_none(self, mock_read_file, _):
        mapper = _build_pg_mapper(mock_read_file)
        # A large render does NOT raise when no limit is injected (None disables).
        with patch.object(mapper, "_plot_interactive_map", return_value="FIG"):
            out = mapper.plot_map(
                _mapping_df(10_000), "pred_ged_sb", interactive=True, max_cells=None
            )
        assert out == "FIG"
