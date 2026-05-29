"""
CIC coverage for HistoricalLineGraph.

Red team: validation failures, C-05 reproduction.
Green team: pure helper methods.
"""

from unittest.mock import MagicMock

import pytest

try:
    from views_reporting.visualizations.historical import HistoricalLineGraph
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)


# ── Red team: validation failures ────────────────────────────────────────


@pytest.mark.red_team
class TestHistoricalLineGraphValidation:

    def test_both_datasets_none_raises(self):
        with pytest.raises(ValueError, match="At least one"):
            HistoricalLineGraph(historical_dataset=None, forecast_dataset=None)

    def test_static_plot_raises_not_implemented(self):
        mock_hist = MagicMock()
        mock_hist._time_id = "month_id"
        mock_hist._entity_values = [1, 2]
        mock_hist.targets = ["ged_sb"]
        mock_hist._time_values = MagicMock()
        mock_hist._time_values.sort_values.return_value = [530]

        hlg = HistoricalLineGraph(historical_dataset=mock_hist)
        with pytest.raises(NotImplementedError):
            hlg.plot_predictions_vs_historical(
                entity_ids=[1], interactive=False
            )

    def test_no_valid_entities_raises(self):
        mock_hist = MagicMock()
        mock_hist._entity_values = [1, 2, 3]
        mock_hist.targets = ["ged_sb"]

        mock_fc = MagicMock()
        mock_fc._entity_values = [4, 5, 6]
        mock_fc.targets = ["pred_ged_sb"]
        mock_fc.sample_size = 1

        hlg = HistoricalLineGraph(
            historical_dataset=mock_hist, forecast_dataset=mock_fc
        )
        with pytest.raises(ValueError, match="No valid entities"):
            hlg._validate_entity_ids([999])

    def test_forecast_only_does_not_crash(self):
        """Forecast-only mode should work (historical_dataset=None).
        C-05 documents that _create_hdi_traces crashes, but with
        sample_size=1 the code takes the simple forecast trace path."""
        import pandas as pd

        mock_fc = MagicMock()
        mock_fc._time_id = "month_id"
        mock_fc._entity_id = "country_id"
        mock_fc._entity_values = [1]
        mock_fc.targets = ["pred_ged_sb"]
        mock_fc.sample_size = 1

        idx = pd.MultiIndex.from_tuples(
            [(528, 1), (529, 1), (530, 1)],
            names=["month_id", "country_id"],
        )
        subset_df = pd.DataFrame(
            {"pred_ged_sb": [1.0, 2.0, 3.0]}, index=idx
        )
        mock_fc.get_subset_dataframe.return_value = subset_df

        hlg = HistoricalLineGraph(
            historical_dataset=None, forecast_dataset=mock_fc
        )
        result = hlg.plot_predictions_vs_historical(
            entity_ids=[1], interactive=True, as_html=True
        )
        assert result is not None


# ── Green team: pure helper methods ──────────────────────────────────────


@pytest.mark.green_team
class TestHistoricalLineGraphHelpers:

    @pytest.fixture
    def hlg(self):
        return HistoricalLineGraph.__new__(HistoricalLineGraph)

    def test_generate_entity_color_format(self, hlg):
        color = hlg._generate_entity_color(0)
        assert color == "hsl(0, 50%, 50%)"

    def test_generate_entity_color_cycles(self, hlg):
        color_9 = hlg._generate_entity_color(9)
        assert "hsl(" in color_9
        hue = int(color_9.split("(")[1].split(",")[0])
        assert hue == (9 * 40) % 360

    def test_get_entity_label_with_map(self, hlg):
        name_map = {1: "Sweden", 2: "Norway"}
        assert hlg._get_entity_label(1, name_map) == "Sweden"

    def test_get_entity_label_missing_id(self, hlg):
        name_map = {1: "Sweden"}
        assert hlg._get_entity_label(999, name_map) == "Entity 999"

    def test_get_entity_label_none_map(self, hlg):
        assert hlg._get_entity_label(42, None) == "Entity 42"
