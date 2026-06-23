"""Value-level characterization tests for MappingModule (frame path).

These pin the *actual rendered values* — the per-(time, entity) target column,
the isoab / country_name join columns, and the row count — that feed the
choropleth. The harness now drives the **views_frames.PredictionFrame** code
path (epic #137, #138), but every numeric literal is unchanged from the original
dataset-driven pin: a green run with identical literals via the frame path is the
proof the migration is behaviour-preserving.

Fixed seed (build_cm_forecast_df seed=42). Floats compared with
np.testing.assert_allclose(atol=1e-4) so float32 noise is not flaky but a real
value change is still caught.
"""

import numpy as np
import pytest

from tests.conftest import (
    build_cm_forecast_df,
    cm_frame_from_df,
    mock_isoab_for_index,
    mock_name_for_index,
)

try:
    from views_frames import SpatialLevel

    import views_reporting.mapping._frame_adapter as frame_adapter
    from views_reporting.mapping.mapping import MappingModule
    from views_reporting.statistics import calculate_map_frame
except ImportError:
    pytest.skip(
        "views_frames or geopandas not installed",
        allow_module_level=True,
    )


def _build_mapper(monkeypatch):
    """CM sample forecast -> calculate_map_frame -> MAP frame -> MappingModule.

    Metadata (get_isoab_for_index/get_name_for_index) is monkeypatched on the
    frame adapter so the test runs offline.
    """
    forecast_df = build_cm_forecast_df(
        n_months=2, n_countries=3, n_samples=40, seed=42
    )
    forecast_frame = cm_frame_from_df(forecast_df, "ged_sb")
    map_df = calculate_map_frame(forecast_frame, "pred_ged_sb")

    # Wrap the collapsed MAP values as an S==1 frame (what forecast.py builds).
    from views_frames import PredictionFrame, SpatioTemporalIndex

    index = SpatioTemporalIndex(
        time=map_df.index.get_level_values("month_id").to_numpy(np.int64),
        unit=map_df.index.get_level_values("country_id").to_numpy(np.int64),
        level=SpatialLevel.CM,
    )
    map_frame = PredictionFrame(
        map_df["pred_ged_sb_map"].to_numpy(np.float32).reshape(-1, 1), index
    )

    monkeypatch.setattr(frame_adapter, "get_isoab_for_index", mock_isoab_for_index)
    monkeypatch.setattr(frame_adapter, "get_name_for_index", mock_name_for_index)
    return MappingModule(
        frame=map_frame,
        level=SpatialLevel.CM,
        target_column="pred_ged_sb_map",
    )


@pytest.mark.green_team
@pytest.mark.slow
class TestMappingSubsetDataframeCharacterization:
    """Pins get_subset_mapping_dataframe(entity_ids=None, time_ids=None)."""

    # Target column produced by calculate_map_frame for the ged_sb forecast.
    TARGET = "pred_ged_sb_map"

    # Expected ordering: time-major (month, country), the from_product layout.
    EXPECTED_MONTHS = [528, 528, 528, 529, 529, 529]
    EXPECTED_COUNTRY_IDS = [1, 2, 3, 1, 2, 3]
    # ISO codes come from REAL_ISO_CODES[(country_id-1) % len] via mock_isoab_for_index.
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
        # The frame adapter emits scalar float32 values per (time, entity);
        # pin the value (np.asarray handles both scalar and any legacy array).
        actual = np.array(
            [float(np.asarray(v).reshape(-1)[0]) for v in view[self.TARGET]]
        )
        np.testing.assert_allclose(
            actual, np.array(self.EXPECTED_VALUES), atol=1e-4
        )
