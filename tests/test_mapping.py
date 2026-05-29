"""
CIC coverage for MappingModule.

Red team: input validation, type checking.
Green team: constructor dispatch, shapefile loading.
"""

from unittest.mock import MagicMock, patch

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
