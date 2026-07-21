"""
Synthetic end-to-end tests for the views-reporting pipeline.

These tests exercise the full workflow chains using synthetic data,
proving that the integration seams between statistics, visualization,
mapping, reports, and templates actually work together.

No network calls, no real prediction data, no WandB.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

try:
    from views_pipeline_core.data.handlers import CMDataset  # noqa: F401  (availability probe)
except ImportError:
    pytest.skip(
        "views_pipeline_core not installed",
        allow_module_level=True,
    )

from tests.conftest import (
    build_cm_forecast_df,
    build_cm_historical_df,
    cm_frame_from_df,
    cm_target_frame_from_df,
    mock_labels_for_index,
    mock_name_for_index,
)
from views_reporting.reports import ReportModule
from views_reporting.statistics import PosteriorDistributionAnalyzer, calculate_map_frame


def _patch_metadata():
    return [
        patch(
            "views_reporting.mapping._frame_adapter.get_labels_for_index",
            side_effect=mock_labels_for_index,
        ),
        patch(
            "views_reporting.visualizations.historical.get_name_for_index",
            side_effect=mock_name_for_index,
        ),
    ]

# ── E2E Level 1: Statistics → Report (no mocks) ─────────────────────────


@pytest.mark.slow
class TestStatisticsToReport:
    """Proves the compute → compose chain works end to end."""

    def test_map_computation_into_report(self, tmp_path):
        """calculate_map() output can be fed into ReportModule and exported."""
        forecast_df = build_cm_forecast_df(n_months=2, n_countries=3, n_samples=30)
        frame = cm_frame_from_df(forecast_df, "ged_sb")

        map_df = calculate_map_frame(frame, "pred_ged_sb")

        assert "pred_ged_sb_map" in map_df.columns
        assert not map_df["pred_ged_sb_map"].isna().all()

        report = ReportModule()
        report.add_heading("Synthetic E2E: MAP Computation", level=1)
        report.add_paragraph(
            f"Computed MAP for {len(map_df)} entity-time pairs."
        )
        report.add_table(
            map_df.reset_index().head(5).to_dict(orient="list")
        )

        with patch(
            "views_reporting.reports.report.PipelineConfig"
        ) as mock_config:
            mock_config.current_version = "0.0.0-test"
            out = tmp_path / "e2e_map_report.html"
            report.export_as_html(str(out))

        assert out.exists()
        html = out.read_text()
        assert "<!DOCTYPE html>" in html
        assert "MAP Computation" in html
        assert "pred_ged_sb_map" in html

    def test_pda_analyze_into_report(self, tmp_path):
        """PDA analysis results can be composed into a report."""
        samples = np.abs(np.random.normal(5, 2, 1000))
        pda = PosteriorDistributionAnalyzer()
        result = pda.analyze(samples, credible_masses=(0.5, 0.9, 0.95))

        report = ReportModule()
        report.add_heading("Posterior Analysis Report", level=1)
        report.add_table({
            "Statistic": ["MAP", "Min", "Max", "Mass at Zero"],
            "Value": [
                f"{result['map']:.3f}",
                f"{result['min']:.3f}",
                f"{result['max']:.3f}",
                f"{result['mass_at_zero']:.3f}",
            ],
        })
        for i, (lo, hi) in enumerate(result["hdis"]):
            report.add_paragraph(
                f"HDI {i}: [{lo:.3f}, {hi:.3f}]"
            )

        with patch(
            "views_reporting.reports.report.PipelineConfig"
        ) as mock_config:
            mock_config.current_version = "0.0.0-test"
            out = tmp_path / "e2e_pda_report.html"
            report.export_as_html(str(out))

        assert out.exists()
        html = out.read_text()
        assert "Posterior Analysis" in html
        assert "MAP" in html


# ── E2E Level 2: Full ForecastReportTemplate pipeline ────────────────────


@pytest.mark.slow
class TestForecastTemplatePipeline:
    """Proves the complete template → mapping → viz → report chain works."""

    @patch("views_reporting.reports.report.PipelineConfig")
    def test_cm_forecast_report_end_to_end(self, mock_config, tmp_path):
        """Full CM forecast report pipeline with synthetic data."""
        from views_reporting.templates.reports.forecast import ForecastReportTemplate

        mock_config.current_version = "0.0.0-test"

        forecast_df = build_cm_forecast_df(
            n_months=2, n_countries=4, n_samples=15
        )
        historical_df = build_cm_historical_df(
            n_months=4, n_countries=4, month_start=524
        )

        mock_model_path = MagicMock()
        mock_model_path.target = "model"
        mock_model_path.model_name = "synthetic_test"
        mock_model_path.reports = tmp_path

        config = {
            "name": "synthetic_test",
            "level": "cm",
            "targets": ["ged_sb"],
        }

        with patch(
            "views_reporting.templates.reports.forecast.generate_model_file_name",
            return_value="synthetic_test_forecast",
        ):
            for p in _patch_metadata():
                p.start()
            try:
                template = ForecastReportTemplate(
                    config=config,
                    model_path=mock_model_path,
                    run_type="forecasting",
                )
                report_path = template.generate(
                    forecast_dataframe=forecast_df,
                    historical_dataframe=historical_df,
                )
            finally:
                patch.stopall()

        assert report_path.exists(), f"Report not created at {report_path}"
        html = report_path.read_text()
        assert "<!DOCTYPE html>" in html
        assert "synthetic_test" in html
        assert "ged_sb" in html
        assert len(html) > 1000, "Report suspiciously small"
        # C-34 provenance footer: build stamp + model/run identity, so the
        # delivered forecast report is self-identifying.
        assert "views-reporting v" in html and "views-frames v" in html
        assert "forecasting" in html  # run_type in the provenance footer

    @patch("views_reporting.reports.report.PipelineConfig")
    def test_cm_point_forecast_report(self, mock_config, tmp_path):
        """Point prediction (sample_size=1) forecast report pipeline."""
        from views_reporting.templates.reports.forecast import ForecastReportTemplate

        mock_config.current_version = "0.0.0-test"

        forecast_df = build_cm_forecast_df(
            n_months=2, n_countries=3, n_samples=1
        )
        historical_df = build_cm_historical_df(
            n_months=4, n_countries=3, month_start=524
        )

        mock_model_path = MagicMock()
        mock_model_path.target = "model"
        mock_model_path.model_name = "point_test"
        mock_model_path.reports = tmp_path

        config = {
            "name": "point_test",
            "level": "cm",
            "targets": ["ged_sb"],
        }

        with patch(
            "views_reporting.templates.reports.forecast.generate_model_file_name",
            return_value="point_test_forecast",
        ):
            for p in _patch_metadata():
                p.start()
            try:
                template = ForecastReportTemplate(
                    config=config,
                    model_path=mock_model_path,
                    run_type="forecasting",
                )
                report_path = template.generate(
                    forecast_dataframe=forecast_df,
                    historical_dataframe=historical_df,
                )
            finally:
                patch.stopall()

        assert report_path.exists()
        html = report_path.read_text()
        assert "<!DOCTYPE html>" in html
        assert len(html) > 1000


# ── E2E Level 2b: HistoricalLineGraph standalone ────────────────────────


@pytest.mark.slow
class TestHistoricalLineGraphPipeline:
    """Proves the visualization → report chain for line graphs."""

    @patch(
        "views_reporting.visualizations.historical.get_name_for_index",
        side_effect=mock_name_for_index,
    )
    def test_historical_vs_forecast_produces_html(self, mock_name, tmp_path):
        """HistoricalLineGraph produces embeddable HTML from synthetic data."""
        from views_frames import SpatialLevel

        from views_reporting.visualizations import HistoricalLineGraph

        historical_df = build_cm_historical_df(
            n_months=6, n_countries=3, month_start=522
        )
        forecast_df = build_cm_forecast_df(
            n_months=3, n_countries=3, n_samples=10, month_start=528
        )

        hist_frame = cm_target_frame_from_df(historical_df, "ged_sb")
        forecast_frame = cm_frame_from_df(forecast_df, "ged_sb")

        graph = HistoricalLineGraph(
            historical_frame=hist_frame,
            forecast_frame=forecast_frame,
            level=SpatialLevel.CM,
        )
        html = graph.plot_predictions_vs_historical(
            entity_ids=[1, 2, 3],
            targets=["ged_sb"],
            as_html=True,
        )

        assert html is not None
        assert len(html) > 500
        assert "plotly" in html.lower() or "div" in html.lower()

        report = ReportModule()
        report.add_heading("Historical vs Forecast", level=1)
        report.add_html(html=html, height=600)

        with patch(
            "views_reporting.reports.report.PipelineConfig"
        ) as mock_config:
            mock_config.current_version = "0.0.0-test"
            out = tmp_path / "e2e_historical.html"
            report.export_as_html(str(out))

        assert out.exists()
        assert len(out.read_text()) > 2000
