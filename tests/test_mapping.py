"""
CIC coverage for MappingModule.

Red team: input validation, type checking.
Green team: constructor dispatch, shapefile loading.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

try:
    from views_pipeline_core.data.handlers import _CDataset, _PGDataset

    from views_reporting.mapping.mapping import MappingModule
except ImportError:
    pytest.skip("views_pipeline_core or geopandas not installed", allow_module_level=True)


# ── Red team: validation ─────────────────────────────────────────────────


@pytest.mark.red_team
class TestMappingModuleValidation:

    def test_invalid_dataset_type_raises(self):
        with pytest.raises((ValueError, AttributeError)):
            MappingModule(views_dataset="not_a_dataset")

    def test_invalid_dataset_mock_raises(self):
        mock = MagicMock()
        with pytest.raises((ValueError, AttributeError)):
            MappingModule(views_dataset=mock)


# ── Green team: constructor dispatch ─────────────────────────────────────


@pytest.mark.green_team
class TestMappingModuleConstructor:

    @patch("views_reporting.mapping.mapping.MappingModule._prepare_base_geojson")
    @patch("views_reporting.mapping.mapping.gpd.read_file")
    def test_pg_dataset_loads_priogrid_shapefile(self, mock_read_file, _):
        mock_gdf = MagicMock()
        mock_gdf.columns = ["gid", "row", "col", "geometry"]
        mock_read_file.return_value = mock_gdf

        mock_dataset = MagicMock(spec=_PGDataset)
        mock_dataset.dataframe = MagicMock()
        mock_dataset._entity_id = "priogrid_id"
        mock_dataset._time_id = "month_id"

        mapper = MappingModule(views_dataset=mock_dataset)
        call_path = str(mock_read_file.call_args[0][0])
        assert "priogrid" in call_path
        assert mapper._location_col == "gid"

    @patch("views_reporting.mapping.mapping.MappingModule._prepare_base_geojson")
    @patch("views_reporting.mapping.mapping.gpd.read_file")
    def test_c_dataset_loads_country_shapefile(self, mock_read_file, _):
        mock_gdf = MagicMock()
        mock_gdf.columns = ["ADM0_A3", "geometry"]
        mock_read_file.return_value = mock_gdf

        mock_dataset = MagicMock(spec=_CDataset)
        mock_dataset.dataframe = MagicMock()
        mock_dataset._entity_id = "country_id"
        mock_dataset._time_id = "month_id"

        mapper = MappingModule(views_dataset=mock_dataset)
        call_path = str(mock_read_file.call_args[0][0])
        assert "country" in call_path
        assert mapper._location_col == "ADM0_A3"


# ── Green team: integration with real shapefiles ─────────────────────────


@pytest.mark.green_team
@pytest.mark.slow
class TestMappingModuleIntegration:

    def test_cm_constructor_loads_real_shapefiles(self, cm_prediction_dataset):
        mapper = MappingModule(views_dataset=cm_prediction_dataset)
        assert mapper._location_col == "ADM0_A3"
        assert mapper._base_geojson is not None
        assert mapper._base_geojson["type"] == "FeatureCollection"


# ── Red team: scale guard (C-26) ─────────────────────────────────────────


def _build_pg_mapper(mock_read_file):
    """A MappingModule over a mocked PGM dataset — no real shapefile, no geojson."""
    mock_gdf = MagicMock()
    mock_gdf.columns = ["gid", "row", "col", "geometry"]
    mock_read_file.return_value = mock_gdf

    mock_dataset = MagicMock(spec=_PGDataset)
    mock_dataset.dataframe = MagicMock()
    mock_dataset._entity_id = "priogrid_id"
    mock_dataset._time_id = "month_id"
    mock_dataset.targets = ["pred_ged_sb"]
    mock_dataset.features = []
    return MappingModule(views_dataset=mock_dataset)


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
