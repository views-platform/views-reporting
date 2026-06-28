"""
CIC coverage for PlotDistribution (frame-native, C-114 / #113).

Red team: input validation.
Green team: rendering correctness, empty data handling.
"""

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest

pytest.importorskip("views_frames")
from views_frames import (  # noqa: E402
    PredictionFrame,
    SpatialLevel,
    SpatioTemporalIndex,
)

from tests.conftest import build_cm_forecast_df, cm_frame_from_df  # noqa: E402
from views_reporting.visualizations.distributions import PlotDistribution  # noqa: E402

matplotlib.use("Agg")


@pytest.fixture
def cm_sample_frame():
    """A real multi-sample CM PredictionFrame for one target."""
    df = build_cm_forecast_df(n_months=3, n_countries=3, n_samples=100, seed=42)
    return cm_frame_from_df(df, "ged_sb")


def _cm_index(times, units):
    return SpatioTemporalIndex(
        time=np.asarray(times, dtype=np.int64),
        unit=np.asarray(units, dtype=np.int64),
        level=SpatialLevel.CM,
    )


def _point_frame():
    """A point (S==1) PredictionFrame — ``is_sample`` is False."""
    return PredictionFrame(
        np.array([[1.0], [2.0]], dtype=np.float32), _cm_index([528, 528], [1, 2])
    )


def _all_nan_frame():
    return PredictionFrame(
        np.full((2, 50), np.nan, dtype=np.float32), _cm_index([528, 528], [1, 2])
    )


# ── Red team: validation ─────────────────────────────────────────────────


@pytest.mark.red_team
class TestPlotDistributionValidation:

    def test_hdi_non_sample_frame_raises(self):
        pd = PlotDistribution(_point_frame())
        with pytest.raises(ValueError, match="sample"):
            pd.plot_highest_density_intervals(alphas=(0.9,))

    def test_hdi_invalid_alpha_raises(self, cm_sample_frame):
        pd = PlotDistribution(cm_sample_frame)
        with pytest.raises(ValueError, match="between 0 and 1"):
            pd.plot_highest_density_intervals(alphas=(1.5,))

    def test_hdi_color_count_mismatch_raises(self, cm_sample_frame):
        pd = PlotDistribution(cm_sample_frame)
        with pytest.raises(ValueError, match="colors"):
            pd.plot_highest_density_intervals(alphas=(0.5, 0.9), colors=["red"])


# ── Green team: rendering correctness ────────────────────────────────────


@pytest.mark.green_team
class TestPlotDistributionRendering:

    def test_map_plot_returns_axes(self, cm_sample_frame):
        pd = PlotDistribution(cm_sample_frame)
        ax = pd.plot_maximum_a_posteriori(var_name="pred_ged_sb")
        assert isinstance(ax, plt.Axes)
        plt.close("all")

    def test_map_plot_empty_data_shows_text(self):
        pd = PlotDistribution(_all_nan_frame())
        ax = pd.plot_maximum_a_posteriori(var_name="pred_ged_sb")
        texts = [t.get_text() for t in ax.texts]
        assert any("No valid samples" in t for t in texts)
        plt.close("all")

    def test_hdi_plot_returns_axes(self, cm_sample_frame):
        pd = PlotDistribution(cm_sample_frame)
        ax = pd.plot_highest_density_intervals(var_name="pred_ged_sb", alphas=(0.9,))
        assert isinstance(ax, plt.Axes)
        plt.close("all")

    def test_map_plot_entity_slice_returns_axes(self, cm_sample_frame):
        """Selecting one entity by id pools only that entity's rows."""
        pd = PlotDistribution(cm_sample_frame)
        ax = pd.plot_maximum_a_posteriori(entity_id=1, var_name="pred_ged_sb")
        assert isinstance(ax, plt.Axes)
        assert len(ax.lines) >= 1
        plt.close("all")
