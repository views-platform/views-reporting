"""Value-level characterization tests for HistoricalLineGraph (current behavior).

Pins the *actual trace y-values* rendered into the plotly Figure — the historical
line, the HDI band bounds, and the MAP/forecast line — per entity, plus the trace
count and the entity dropdown labels. This catches a subtle regression (wrong value
on a series, misaligned entity, dropped trace) when these modules migrate to consume
views_frames.PredictionFrame.

Fixed seeds. Floats compared with np.testing.assert_allclose(atol=1e-4) so float32
noise is not flaky but a real value change is still caught. We call the lower-level
_plot_interactive(..., as_html=False) to obtain the Figure object directly (the
public plot_predictions_vs_historical only returns HTML/None), passing map_df and
cutoff_label/caption the same way the public path does.
"""

import numpy as np
import pytest

from tests.conftest import (
    build_cm_forecast_df,
    build_cm_historical_df,
    mock_name_for_df,
)

try:
    from views_pipeline_core.data.handlers import CMDataset

    import views_reporting.visualizations.historical as historical_module
    from views_reporting.statistics import calculate_map
    from views_reporting.visualizations import HistoricalLineGraph
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)


def _trace_y(trace):
    return np.asarray(trace.y, dtype=float)


def _build_figure(monkeypatch):
    """Two-country CM hist + 40-sample CM forecast -> HDI Figure.

    get_name is monkeypatched on the name imported into
    views_reporting.visualizations.historical, mirroring the existing tests, so
    the graph uses deterministic "Country N" labels offline.
    """
    historical_df = build_cm_historical_df(
        n_months=6, n_countries=2, month_start=522, seed=99
    )
    forecast_df = build_cm_forecast_df(
        n_months=3, n_countries=2, n_samples=40, month_start=528, seed=42
    )
    hist_ds = CMDataset(historical_df, targets=["ged_sb"])
    forecast_ds = CMDataset(forecast_df)

    monkeypatch.setattr(
        historical_module,
        "get_name",
        lambda ds, **kw: mock_name_for_df(ds.dataframe, ds._entity_id, ds._time_id),
    )

    graph = HistoricalLineGraph(
        historical_dataset=hist_ds, forecast_dataset=forecast_ds
    )
    map_df = calculate_map(forecast_ds, features=["pred_ged_sb"], alpha=0.9)
    fig = graph._plot_interactive(
        entity_ids=[1, 2],
        target="ged_sb",
        alpha=0.9,
        vline=528,
        hdi=True,
        as_html=False,
        map_df=map_df,
        cutoff_label="Forecast Start",
        caption="CAP",
    )
    return fig


@pytest.mark.green_team
@pytest.mark.slow
class TestHistoricalFigureCharacterization:
    """Pins the Figure produced by _plot_interactive for a 2-entity HDI render.

    Trace layout (current behavior), per entity, in order:
      [Historical, HDI lower, HDI upper, HDI fill, MAP]
    -> 5 traces per entity, 10 total for 2 entities. The first entity's traces
    are visible; the second entity's start hidden (driven by the dropdown).
    """

    # Historical line, country 1 (months 522..527), rounded 5dp.
    HIST_C1 = [1.85764, 2.28326, 1.84538, 2.75518, 1.88693, 1.83295]
    HIST_C2 = [4.05722, 3.32981, 1.93097, 2.82565, 0.36784, 2.6854]

    # 90% HDI band bounds for country 1, forecast months 528..530.
    HDI_LOWER_C1 = [0.86288, 0.80473, 0.72773]
    HDI_UPPER_C1 = [5.77842, 5.21684, 4.73789]

    # 90% HDI band bounds for country 2.
    HDI_LOWER_C2 = [0.92962, 0.58878, 0.03771]
    HDI_UPPER_C2 = [5.34697, 5.10419, 4.70335]

    # MAP line y-values as currently rendered (map_df.xs(entity)[...map] series).
    MAP_C1 = [2.31907, 1.79796, 4.25338]
    MAP_C2 = [2.5496, 3.35178, 3.7528]

    def test_trace_count_and_names(self, monkeypatch):
        fig = _build_figure(monkeypatch)
        assert len(fig.data) == 10
        names = [t.name for t in fig.data]
        assert names == [
            "Country 1 (Historical)",
            "90% HDI", "90% HDI", "90% HDI",
            "Country 1 (MAP)",
            "Country 2 (Historical)",
            "90% HDI", "90% HDI", "90% HDI",
            "Country 2 (MAP)",
        ]

    def test_dropdown_labels(self, monkeypatch):
        fig = _build_figure(monkeypatch)
        assert fig.layout.updatemenus, "expected a dropdown for 2 entities"
        labels = [b.label for b in fig.layout.updatemenus[0].buttons]
        assert labels == ["Country 1", "Country 2"]

    def test_historical_line_values(self, monkeypatch):
        fig = _build_figure(monkeypatch)
        np.testing.assert_allclose(
            _trace_y(fig.data[0]), np.array(self.HIST_C1), atol=1e-4
        )
        np.testing.assert_allclose(
            _trace_y(fig.data[5]), np.array(self.HIST_C2), atol=1e-4
        )

    def test_hdi_band_bounds(self, monkeypatch):
        fig = _build_figure(monkeypatch)
        # Country 1 band: trace 1 = lower, trace 2 = upper.
        np.testing.assert_allclose(
            _trace_y(fig.data[1]), np.array(self.HDI_LOWER_C1), atol=1e-4
        )
        np.testing.assert_allclose(
            _trace_y(fig.data[2]), np.array(self.HDI_UPPER_C1), atol=1e-4
        )
        # Country 2 band: trace 6 = lower, trace 7 = upper.
        np.testing.assert_allclose(
            _trace_y(fig.data[6]), np.array(self.HDI_LOWER_C2), atol=1e-4
        )
        np.testing.assert_allclose(
            _trace_y(fig.data[7]), np.array(self.HDI_UPPER_C2), atol=1e-4
        )

    def test_hdi_fill_is_upper_then_reversed_lower(self, monkeypatch):
        """The fill trace (country 1, index 3) closes the polygon: upper bounds
        followed by the lower bounds reversed."""
        fig = _build_figure(monkeypatch)
        expected = self.HDI_UPPER_C1 + self.HDI_LOWER_C1[::-1]
        np.testing.assert_allclose(
            _trace_y(fig.data[3]), np.array(expected), atol=1e-4
        )

    def test_map_line_values(self, monkeypatch):
        fig = _build_figure(monkeypatch)
        np.testing.assert_allclose(
            _trace_y(fig.data[4]), np.array(self.MAP_C1), atol=1e-4
        )
        np.testing.assert_allclose(
            _trace_y(fig.data[9]), np.array(self.MAP_C2), atol=1e-4
        )

    def test_initial_visibility_first_entity_only(self, monkeypatch):
        """Current behavior: entity-1 traces visible, entity-2 traces hidden."""
        fig = _build_figure(monkeypatch)
        assert [t.visible for t in fig.data[0:5]] == [True, True, True, True, True]
        assert [t.visible for t in fig.data[5:10]] == [
            False, False, False, False, False,
        ]
