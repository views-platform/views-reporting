"""
CIC coverage for PlotDistribution.

Red team: input validation.
Green team: rendering correctness, empty data handling.
"""

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest

try:
    from views_reporting.visualizations.distributions import PlotDistribution
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)

matplotlib.use("Agg")


# ── Red team: validation ─────────────────────────────────────────────────


@pytest.mark.red_team
class TestPlotDistributionValidation:

    def test_map_invalid_var_none_raises(self, mock_views_dataset):
        pd = PlotDistribution(dataset=mock_views_dataset)
        with pytest.raises(ValueError, match="Invalid variable"):
            pd.plot_maximum_a_posteriori(var_name=None)

    def test_map_invalid_var_not_in_targets_raises(self, mock_views_dataset):
        pd = PlotDistribution(dataset=mock_views_dataset)
        with pytest.raises(ValueError, match="Invalid variable"):
            pd.plot_maximum_a_posteriori(var_name="nonexistent")

    def test_hdi_non_prediction_raises(self, mock_views_dataset):
        mock_views_dataset.is_prediction = False
        pd = PlotDistribution(dataset=mock_views_dataset)
        with pytest.raises(ValueError, match="prediction"):
            pd.plot_highest_density_intervals(
                var_name="pred_ged_sb", alphas=(0.9,)
            )

    def test_hdi_invalid_alpha_raises(self, mock_views_dataset):
        pd = PlotDistribution(dataset=mock_views_dataset)
        with pytest.raises(ValueError, match="between 0 and 1"):
            pd.plot_highest_density_intervals(
                var_name="pred_ged_sb", alphas=(1.5,)
            )

    def test_hdi_color_count_mismatch_raises(self, mock_views_dataset):
        pd = PlotDistribution(dataset=mock_views_dataset)
        with pytest.raises(ValueError, match="colors"):
            pd.plot_highest_density_intervals(
                var_name="pred_ged_sb",
                alphas=(0.5, 0.9),
                colors=["red"],
            )


# ── Green team: rendering correctness ────────────────────────────────────


@pytest.mark.green_team
class TestPlotDistributionRendering:

    def test_map_plot_returns_axes(self, mock_views_dataset):
        pd = PlotDistribution(dataset=mock_views_dataset)
        ax = pd.plot_maximum_a_posteriori(var_name="pred_ged_sb")
        assert isinstance(ax, plt.Axes)
        plt.close("all")

    def test_map_plot_empty_data_shows_text(self, mock_views_dataset):
        nan_tensor = np.full((3, 3, 100, 1), np.nan)
        mock_views_dataset.to_tensor.return_value = nan_tensor
        pd = PlotDistribution(dataset=mock_views_dataset)
        ax = pd.plot_maximum_a_posteriori(var_name="pred_ged_sb")
        texts = [t.get_text() for t in ax.texts]
        assert any("No valid samples" in t for t in texts)
        plt.close("all")

    def test_hdi_plot_returns_axes(self, mock_views_dataset):
        pd = PlotDistribution(dataset=mock_views_dataset)
        ax = pd.plot_highest_density_intervals(
            var_name="pred_ged_sb", alphas=(0.9,)
        )
        assert isinstance(ax, plt.Axes)
        plt.close("all")
