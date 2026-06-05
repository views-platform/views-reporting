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


# ── Green team: integration with real CMDataset ──────────────────────────


@pytest.mark.green_team
class TestHistoricalLineGraphIntegration:

    def test_forecast_only_with_real_dataset(self, cm_prediction_dataset):
        """Forecast-only with sample_size=1 dataset (no HDI path)."""
        import pandas as pd

        idx = pd.MultiIndex.from_tuples(
            [(528, 1), (529, 1), (530, 1)],
            names=["month_id", "country_id"],
        )
        scalar_df = pd.DataFrame(
            {"pred_ged_sb": [1.0, 2.0, 3.0]}, index=idx
        )
        try:
            from views_pipeline_core.data.handlers import CMDataset
        except ImportError:
            pytest.skip("views_pipeline_core not installed")
        scalar_ds = CMDataset(source=scalar_df)

        hlg = HistoricalLineGraph(
            historical_dataset=None, forecast_dataset=scalar_ds
        )
        result = hlg.plot_predictions_vs_historical(
            entity_ids=[1], interactive=True, as_html=True
        )
        assert result is not None
        assert "scatter" in result.lower() or "plotly" in result.lower()

    def test_forecast_only_with_hdi_renders_bands(self):
        """C-05: forecast-only with sample_size > 1 should render HDI bands,
        not silently drop them via the except Exception fallback."""
        import logging

        import numpy as np
        import pandas as pd

        try:
            from views_pipeline_core.data.handlers import CMDataset
        except ImportError:
            pytest.skip("views_pipeline_core not installed")

        np.random.seed(42)
        idx = pd.MultiIndex.from_tuples(
            [(528, 1), (529, 1), (530, 1)],
            names=["month_id", "country_id"],
        )
        samples = [np.random.normal(5, 2, 50) for _ in range(3)]
        df = pd.DataFrame({"pred_ged_sb": samples}, index=idx)
        forecast_ds = CMDataset(source=df)

        hlg = HistoricalLineGraph(
            historical_dataset=None, forecast_dataset=forecast_ds
        )

        errors = []
        original_error = logging.getLogger(
            "views_reporting.visualizations.historical"
        ).error

        def capture_error(msg, *args, **kwargs):
            errors.append(msg)
            original_error(msg, *args, **kwargs)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                logging.getLogger("views_reporting.visualizations.historical"),
                "error",
                capture_error,
            )
            result = hlg.plot_predictions_vs_historical(
                entity_ids=[1], interactive=True, as_html=True
            )

        assert result is not None
        hdi_errors = [e for e in errors if "HDI" in str(e) or "hdi" in str(e)]
        assert len(hdi_errors) == 0, (
            f"HDI bands silently dropped with errors: {hdi_errors}"
        )


# ── Green team: hindcast vs forecast cutoff annotation (Phase A falsify) ──


@pytest.mark.green_team
class TestHindcastCutoffAnnotation:
    """The cutoff line + label must reflect whether predictions overlay
    observed history (a hindcast — e.g. calibration rolling-origin) or extend
    beyond it (a true forecast). Predictions are always plotted at their own
    month_ids; the data property max(pred) <= max(observed) decides the mode."""

    @staticmethod
    def _datasets(hist_months, pred_months):
        import numpy as np
        import pandas as pd
        from views_pipeline_core.data.handlers import CMDataset

        hidx = pd.MultiIndex.from_product(
            [list(hist_months), [1]], names=["month_id", "country_id"]
        )
        hist = CMDataset(
            source=pd.DataFrame(
                {"ged_sb": np.linspace(1.0, 5.0, len(hidx))}, index=hidx
            ),
            targets=["ged_sb"],
        )
        pidx = pd.MultiIndex.from_product(
            [list(pred_months), [1]], names=["month_id", "country_id"]
        )
        fc = CMDataset(
            source=pd.DataFrame(
                {"pred_ged_sb": [float(i) for i in range(len(pidx))]}, index=pidx
            )
        )
        return hist, fc

    @pytest.fixture(autouse=True)
    def _no_viewser(self, monkeypatch):
        """Avoid live viewser metadata; graph falls back to 'Entity N' labels."""
        def boom(*a, **k):
            raise RuntimeError("viewser disabled in test")

        monkeypatch.setattr(
            "views_reporting.visualizations.historical.get_name", boom
        )

    def _skip_if_no_core(self):
        try:
            import views_pipeline_core.data.handlers  # noqa: F401
        except ImportError:
            pytest.skip("views_pipeline_core not installed")

    def test_hindcast_when_predictions_within_observed(self):
        """Predictions 110-115 inside observed 100-130 -> hindcast label + caption,
        NOT 'Forecast Start'."""
        self._skip_if_no_core()
        hist, fc = self._datasets(range(100, 131), range(110, 116))
        html = HistoricalLineGraph(
            historical_dataset=hist, forecast_dataset=fc
        ).plot_predictions_vs_historical(entity_ids=[1], as_html=True)
        assert "Forecast launched (hindcast)" in html
        assert "hindcast" in html.lower()  # caption present
        assert "Forecast Start" not in html

    def test_true_forecast_when_predictions_beyond_observed(self):
        """Predictions 131-136 beyond observed 100-130 -> 'Forecast Start', no hindcast."""
        self._skip_if_no_core()
        hist, fc = self._datasets(range(100, 131), range(131, 137))
        html = HistoricalLineGraph(
            historical_dataset=hist, forecast_dataset=fc
        ).plot_predictions_vs_historical(entity_ids=[1], as_html=True)
        assert "Forecast Start" in html
        assert "hindcast" not in html.lower()

    def test_cutoff_line_at_launch_month_with_label_and_caption(self):
        """Figure-level: hindcast cutoff line sits at the first predicted month
        (launch), carries the hindcast label, and the caption is the title."""
        self._skip_if_no_core()
        hist, fc = self._datasets(range(100, 131), range(110, 116))
        g = HistoricalLineGraph(historical_dataset=hist, forecast_dataset=fc)
        fig = g._plot_interactive(
            entity_ids=[1],
            target="ged_sb",
            alpha=0.9,
            vline=110,
            hdi=False,
            as_html=False,
            map_df=None,
            cutoff_label="Forecast launched (hindcast)",
            caption="CAPTION-MARKER",
        )
        assert any(getattr(s, "x0", None) == 110 for s in fig.layout.shapes)
        ann_text = " ".join((a.text or "") for a in fig.layout.annotations)
        assert "hindcast" in ann_text.lower()
        assert fig.layout.title.text == "CAPTION-MARKER"

    def test_partition_name_shown_when_run_type_given(self):
        """The authoritative partition name (run_type) is shown verbatim in the caption."""
        self._skip_if_no_core()
        hist, fc = self._datasets(range(100, 131), range(110, 116))
        html = HistoricalLineGraph(
            historical_dataset=hist, forecast_dataset=fc
        ).plot_predictions_vs_historical(
            entity_ids=[1], as_html=True, run_type="calibration"
        )
        assert "Calibration partition" in html
        assert "hindcast" in html.lower()

    def test_dropdown_does_not_clobber_caption_title(self):
        """Regression: switching country via the dropdown must NOT wipe the
        caption, which lives in the figure title (the dropdown previously
        relayouted the title per entity)."""
        self._skip_if_no_core()
        import numpy as np
        import pandas as pd
        from views_pipeline_core.data.handlers import CMDataset

        countries = [1, 2]
        hidx = pd.MultiIndex.from_product(
            [list(range(100, 131)), countries], names=["month_id", "country_id"]
        )
        hist = CMDataset(
            source=pd.DataFrame(
                {"ged_sb": np.linspace(1.0, 5.0, len(hidx))}, index=hidx
            ),
            targets=["ged_sb"],
        )
        pidx = pd.MultiIndex.from_product(
            [list(range(110, 116)), countries], names=["month_id", "country_id"]
        )
        fc = CMDataset(
            source=pd.DataFrame(
                {"pred_ged_sb": [float(i) for i in range(len(pidx))]}, index=pidx
            )
        )
        fig = HistoricalLineGraph(
            historical_dataset=hist, forecast_dataset=fc
        )._plot_interactive(
            entity_ids=[1, 2],
            target="ged_sb",
            alpha=0.9,
            vline=110,
            hdi=False,
            as_html=False,
            map_df=None,
            cutoff_label="Forecast launched (hindcast)",
            caption="PERSIST-CAPTION",
        )
        assert fig.layout.updatemenus, "expected a dropdown for >1 entity"
        for btn in fig.layout.updatemenus[0].buttons:
            for arg in btn.args:
                assert "title" not in (arg or {}), (
                    "dropdown button must not relayout the title (wipes caption)"
                )
        assert fig.layout.title.text == "PERSIST-CAPTION"


# ── Green team: HDI credible level is visible in the legend (#88, Q1) ─────


@pytest.mark.green_team
class TestHdiLevelLabel:
    """The HDI band's credible level must be readable from the report itself."""

    def _forecast_ds(self):
        import numpy as np
        import pandas as pd

        try:
            from views_pipeline_core.data.handlers import CMDataset
        except ImportError:
            pytest.skip("views_pipeline_core not installed")

        np.random.seed(42)
        idx = pd.MultiIndex.from_tuples(
            [(528, 1), (529, 1), (530, 1)],
            names=["month_id", "country_id"],
        )
        samples = [np.random.normal(5, 2, 50) for _ in range(3)]
        df = pd.DataFrame({"pred_ged_sb": samples}, index=idx)
        return CMDataset(source=df)

    def test_hdi_legend_shows_default_level(self):
        hlg = HistoricalLineGraph(
            historical_dataset=None, forecast_dataset=self._forecast_ds()
        )
        html = hlg.plot_predictions_vs_historical(
            entity_ids=[1], interactive=True, as_html=True, alpha=0.9
        )
        assert "90% HDI" in html

    def test_hdi_legend_reflects_alpha(self):
        """The level shown is the alpha passed in, not a hardcoded string."""
        hlg = HistoricalLineGraph(
            historical_dataset=None, forecast_dataset=self._forecast_ds()
        )
        html = hlg.plot_predictions_vs_historical(
            entity_ids=[1], interactive=True, as_html=True, alpha=0.95
        )
        assert "95% HDI" in html
        assert "90% HDI" not in html


# ── Tag-based dropdown visibility (#89, fixes CIC Deviation #5) ───────────


def _two_entity_forecast_ds():
    import numpy as np
    import pandas as pd

    try:
        from views_pipeline_core.data.handlers import CMDataset
    except ImportError:
        pytest.skip("views_pipeline_core not installed")

    np.random.seed(0)
    idx = pd.MultiIndex.from_product(
        [[528, 529, 530], [1, 2]], names=["month_id", "country_id"]
    )
    samples = [np.random.normal(5, 2, 50) for _ in range(len(idx))]
    df = pd.DataFrame({"pred_ged_sb": samples}, index=idx)
    return CMDataset(source=df)


@pytest.mark.green_team
class TestDropdownVisibilityUniform:
    """The entity dropdown's visibility arrays must match the actual traces."""

    def test_visibility_partitions_traces(self):
        hlg = HistoricalLineGraph(
            historical_dataset=None, forecast_dataset=_two_entity_forecast_ds()
        )
        fig = hlg._plot_interactive(
            entity_ids=[1, 2], target="ged_sb", alpha=0.9,
            vline=None, hdi=True, as_html=False, map_df=None,
        )
        assert fig.layout.updatemenus, "expected a dropdown for >1 entity"
        n = len(fig.data)
        buttons = fig.layout.updatemenus[0].buttons
        for btn in buttons:
            assert len(btn.args[0]["visible"]) == n, (
                "visibility array must match the number of traces"
            )
        b0 = [bool(v) for v in buttons[0].args[0]["visible"]]
        b1 = [bool(v) for v in buttons[1].args[0]["visible"]]
        # each button shows one entity; together they partition all traces
        assert sum(b0) + sum(b1) == n
        assert all(not (x and y) for x, y in zip(b0, b1)), "buttons must be disjoint"


@pytest.mark.red_team
class TestDropdownVisibilityVariableCounts:
    """CIC Deviation #5: when HDI fails for one entity it falls back to a
    single forecast trace, so entities have *different* trace counts. The
    dropdown must stay aligned (the old index-arithmetic broke here)."""

    def test_hdi_failure_keeps_dropdown_aligned(self):
        hlg = HistoricalLineGraph(
            historical_dataset=None, forecast_dataset=_two_entity_forecast_ds()
        )
        original = hlg._get_hdi_data

        def hdi_fails_for_entity_2(entity_id, target, alpha):
            if entity_id == 2:
                raise RuntimeError("simulated HDI failure for entity 2")
            return original(entity_id, target, alpha)

        hlg._get_hdi_data = hdi_fails_for_entity_2

        fig = hlg._plot_interactive(
            entity_ids=[1, 2], target="ged_sb", alpha=0.9,
            vline=None, hdi=True, as_html=False, map_df=None,
        )

        n = len(fig.data)
        # entity 1 -> 3 HDI traces; entity 2 -> 1 fallback forecast trace
        assert n == 4
        buttons = fig.layout.updatemenus[0].buttons
        for btn in buttons:
            assert len(btn.args[0]["visible"]) == n, (
                f"visibility length {len(btn.args[0]['visible'])} != trace count {n} "
                "(index-arithmetic assumed a uniform traces-per-entity)"
            )
        assert sum(bool(v) for v in buttons[0].args[0]["visible"]) == 3  # entity 1
        assert sum(bool(v) for v in buttons[1].args[0]["visible"]) == 1  # entity 2


# ── Multi-level HDI bands + legend chooser (#90) ─────────────────────────


@pytest.mark.green_team
class TestHdiLevelSelector:
    """The reader selects the HDI level live via the legend (90% default;
    95%/99% start collapsed to legend entries)."""

    def _ds(self, n_entities=1):
        import numpy as np
        import pandas as pd

        try:
            from views_pipeline_core.data.handlers import CMDataset
        except ImportError:
            pytest.skip("views_pipeline_core not installed")

        np.random.seed(1)
        countries = list(range(1, n_entities + 1))
        idx = pd.MultiIndex.from_product(
            [[528, 529, 530], countries], names=["month_id", "country_id"]
        )
        samples = [np.random.normal(5, 2, 50) for _ in range(len(idx))]
        return CMDataset(source=pd.DataFrame({"pred_ged_sb": samples}, index=idx))

    def _fig(self, n_entities, entity_ids):
        hlg = HistoricalLineGraph(
            historical_dataset=None, forecast_dataset=self._ds(n_entities)
        )
        return hlg._plot_interactive(
            entity_ids=entity_ids, target="ged_sb", alpha=0.9,
            hdi_levels=[0.9, 0.95, 0.99], vline=None, hdi=True,
            as_html=False, map_df=None,
        )

    def test_one_legend_entry_per_level(self):
        fig = self._fig(1, [1])
        legend_names = [t.name for t in fig.data if t.showlegend]
        for pct in ("90% HDI", "95% HDI", "99% HDI"):
            assert legend_names.count(pct) == 1, f"expected exactly one '{pct}' entry"

    def test_default_visible_others_legendonly(self):
        fig = self._fig(1, [1])

        def states(pct):
            return {t.visible for t in fig.data if t.name == f"{pct}% HDI"}

        assert states("90") == {True}          # default level shown
        assert states("95") == {"legendonly"}  # collapsed to a legend toggle
        assert states("99") == {"legendonly"}

    def test_band_traces_share_legendgroup_per_level(self):
        fig = self._fig(1, [1])
        g90 = {t.legendgroup for t in fig.data if t.name == "90% HDI"}
        g95 = {t.legendgroup for t in fig.data if t.name == "95% HDI"}
        assert len(g90) == 1, "the 3 traces of a band must share one legendgroup"
        assert g90 != g95, "each level must have a distinct legendgroup"

    def test_multientity_dropdown_three_state(self):
        fig = self._fig(2, [1, 2])
        buttons = fig.layout.updatemenus[0].buttons
        n = len(fig.data)
        # 2 entities x 3 levels x 3 traces = 18
        assert n == 18
        b0 = list(buttons[0].args[0]["visible"])
        assert len(b0) == n
        # entity-1 button: 3 default-level True, 6 other-level legendonly,
        # 9 (entity-2) hidden
        assert b0.count(True) == 3
        assert b0.count("legendonly") == 6
        assert b0.count(False) == 9
