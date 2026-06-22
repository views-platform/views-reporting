"""Value-level characterization tests for MappingModule (current behavior).

These pin the *actual rendered values* — the per-(time, entity) target column,
the isoab / country_name join columns, and the row count — that feed the
choropleth, so the upcoming views_frames.PredictionFrame migration can be proven
behavior-preserving. The join + value alignment is exactly what the frame adapter
will change, so it is pinned here against the current code.

Fixed seed (build_cm_forecast_df seed=42). Floats compared with
np.testing.assert_allclose(atol=1e-4) so float32 noise is not flaky but a real
value change is still caught.
"""

import numpy as np
import pytest

from tests.conftest import (
    build_cm_forecast_df,
    mock_isoab_for_df,
    mock_name_for_df,
)

try:
    from views_pipeline_core.data.handlers import CMDataset

    import views_reporting.mapping.mapping as mapping_module
    from views_reporting.mapping.mapping import MappingModule
    from views_reporting.statistics import calculate_map
except ImportError:
    pytest.skip(
        "views_pipeline_core or geopandas not installed",
        allow_module_level=True,
    )


def _build_mapper(monkeypatch):
    """CM sample forecast -> calculate_map -> MAP CMDataset -> MappingModule.

    Metadata (get_isoab/get_name) is monkeypatched on the names imported into
    views_reporting.mapping.mapping, exactly as the existing e2e tests do, so the
    test runs offline.
    """
    forecast_df = build_cm_forecast_df(
        n_months=2, n_countries=3, n_samples=40, seed=42
    )
    forecast_ds = CMDataset(source=forecast_df)
    map_df = calculate_map(forecast_ds, features=["pred_ged_sb"], alpha=0.9)
    map_ds = CMDataset(source=map_df.copy())

    monkeypatch.setattr(
        mapping_module,
        "get_isoab",
        lambda ds: mock_isoab_for_df(ds.dataframe, ds._entity_id, ds._time_id),
    )
    monkeypatch.setattr(
        mapping_module,
        "get_name",
        lambda ds, **kw: mock_name_for_df(ds.dataframe, ds._entity_id, ds._time_id),
    )
    return MappingModule(views_dataset=map_ds)


@pytest.mark.green_team
@pytest.mark.slow
class TestMappingSubsetDataframeCharacterization:
    """Pins get_subset_mapping_dataframe(entity_ids=None, time_ids=None)."""

    # Target column produced by calculate_map for the ged_sb forecast.
    TARGET = "pred_ged_sb_map"

    # Expected ordering: time-major (month, country), the from_product layout.
    EXPECTED_MONTHS = [528, 528, 528, 529, 529, 529]
    EXPECTED_COUNTRY_IDS = [1, 2, 3, 1, 2, 3]
    # ISO codes come from REAL_ISO_CODES[(country_id-1) % len] via mock_isoab_for_df.
    EXPECTED_ISOAB = ["TZA", "CAN", "USA", "TZA", "CAN", "USA"]
    EXPECTED_NAMES = [
        "Country 1", "Country 2", "Country 3",
        "Country 1", "Country 2", "Country 3",
    ]
    # MAP estimate values per (time, entity), rounded to 5 dp.
    EXPECTED_VALUES = [2.31907, 2.5496, 1.79796, 3.35178, 4.25338, 3.7528]

    def _ordered_view(self, mapper):
        out = mapper.get_subset_mapping_dataframe(entity_ids=None, time_ids=None)
        view = (
            out[["month_id", "country_id", "isoab", "country_name", self.TARGET]]
            .sort_values(["month_id", "country_id"])
            .reset_index(drop=True)
        )
        return out, view

    def test_row_count(self, monkeypatch):
        mapper = _build_mapper(monkeypatch)
        out, _ = self._ordered_view(mapper)
        # 2 months x 3 countries, all geometries resolved (no drops).
        assert len(out) == 6

    def test_join_columns_per_entity(self, monkeypatch):
        mapper = _build_mapper(monkeypatch)
        _, view = self._ordered_view(mapper)
        assert view["month_id"].astype(int).tolist() == self.EXPECTED_MONTHS
        assert view["country_id"].astype(int).tolist() == self.EXPECTED_COUNTRY_IDS
        assert view["isoab"].tolist() == self.EXPECTED_ISOAB
        assert view["country_name"].tolist() == self.EXPECTED_NAMES

    def test_target_values_per_time_entity(self, monkeypatch):
        mapper = _build_mapper(monkeypatch)
        _, view = self._ordered_view(mapper)
        # The target column holds single-element float32 arrays at this stage
        # (plot_map later squeezes them); pin the scalar value inside each.
        actual = np.array(
            [float(np.asarray(v).reshape(-1)[0]) for v in view[self.TARGET]]
        )
        np.testing.assert_allclose(
            actual, np.array(self.EXPECTED_VALUES), atol=1e-4
        )
