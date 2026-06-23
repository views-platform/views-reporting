"""
End-to-end tests using real fixture data from tests/data/.

Two formats tested:
1. Parquet → frames (point estimates): average_cmbaseline, average_pgmbaseline
2. NumPy → PredictionFrame (sample estimates): red_ranger

Tests skip when fixture data is absent (CI, other machines).
See tests/data/README.md for setup instructions.
"""

import glob
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

try:
    from views_frames import PredictionFrame  # noqa: F401
except ImportError:
    pytest.skip("views_frames not installed", allow_module_level=True)

from tests.conftest import mock_isoab_for_index, mock_name_for_index
from views_reporting.loaders import load_predictions
from views_reporting.statistics import calculate_map_frame

logger = logging.getLogger(__name__)

FIXTURE_DIR = Path(__file__).parent / "data"


def _load_manifest(model_name):
    """Load manifest.json for a fixture model, or skip."""
    manifest_path = FIXTURE_DIR / model_name / "manifest.json"
    if not manifest_path.exists():
        pytest.skip(f"Fixture not found: {manifest_path}")
    return json.loads(manifest_path.read_text())


def _discover_parquet_origins(model_dir, manifest):
    """Find all prediction parquet files for a model, sorted by origin."""
    ts = manifest["run_timestamp"]
    pattern = str(model_dir / f"predictions_calibration_{ts}_*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        pytest.skip(f"No prediction parquets in {model_dir}")
    return files


def _load_historical(model_dir):
    """Load the historical viewser DataFrame."""
    hist_path = model_dir / "calibration_viewser_df.parquet"
    if not hist_path.exists():
        return None
    return pd.read_parquet(hist_path)


def _patch_metadata():
    """Patch the index-keyed metadata accessors used by the frame path."""
    return [
        patch(
            "views_reporting.mapping._frame_adapter.get_isoab_for_index",
            side_effect=mock_isoab_for_index,
        ),
        patch(
            "views_reporting.mapping._frame_adapter.get_name_for_index",
            side_effect=mock_name_for_index,
        ),
        patch(
            "views_reporting.visualizations.historical.get_name_for_index",
            side_effect=mock_name_for_index,
        ),
    ]


# ── Format 1: Parquet point estimates ────────────────────────────────────


@pytest.mark.slow
class TestParquetPointEstimates:
    """E2E tests for parquet DataFrame models (average baselines)."""

    @pytest.mark.parametrize("model_name", ["average_cmbaseline", "average_pgmbaseline"])
    def test_frame_creation(self, model_name):
        """Parquet fixture loads into a per-target PredictionFrame via loader."""
        manifest = _load_manifest(model_name)
        model_dir = FIXTURE_DIR / model_name
        origins = _discover_parquet_origins(model_dir, manifest)

        frames = load_predictions(
            "dataframe", Path(origins[0]), manifest["level"], manifest["targets"]
        )

        target = manifest["targets"][0]
        assert isinstance(frames[target], PredictionFrame)
        assert frames[target].sample_count == 1

    @pytest.mark.parametrize("model_name", ["average_cmbaseline", "average_pgmbaseline"])
    def test_all_13_origins_load(self, model_name):
        """All 13 rolling origins load successfully via loader."""
        manifest = _load_manifest(model_name)
        model_dir = FIXTURE_DIR / model_name
        origins = _discover_parquet_origins(model_dir, manifest)

        assert len(origins) == 13, f"Expected 13 origins, got {len(origins)}"
        target = manifest["targets"][0]
        for path in origins:
            frames = load_predictions(
                "dataframe", Path(path), manifest["level"], manifest["targets"]
            )
            assert isinstance(frames[target], PredictionFrame)

    @patch("views_reporting.reports.report.PipelineConfig")
    def test_cm_point_forecast_report(self, mock_config, tmp_path):
        """Full forecast report from average_cmbaseline real data."""
        from views_reporting.templates.reports.forecast import ForecastReportTemplate

        manifest = _load_manifest("average_cmbaseline")
        model_dir = FIXTURE_DIR / "average_cmbaseline"
        origins = _discover_parquet_origins(model_dir, manifest)

        forecast_df = pd.read_parquet(origins[0])
        historical_df = _load_historical(model_dir)

        mock_config.current_version = "0.0.0-fixture-test"

        mock_model_path = MagicMock()
        mock_model_path.target = "model"
        mock_model_path.model_name = "average_cmbaseline"
        mock_model_path.reports = tmp_path

        config = {
            "name": "average_cmbaseline",
            "level": "cm",
            "targets": manifest["targets"],
        }

        with patch(
            "views_reporting.templates.reports.forecast.generate_model_file_name",
            return_value="average_cmbaseline_fixture",
        ):
            for p in _patch_metadata():
                p.start()
            try:
                template = ForecastReportTemplate(
                    config=config,
                    model_path=mock_model_path,
                    run_type="calibration",
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
        assert "average_cmbaseline" in html
        assert len(html) > 5000
        logger.info(f"CM point report: {len(html)} bytes")


# ── Format 2: NumPy PredictionFrame sample estimates ─────────────────────


@pytest.mark.slow
class TestPredictionFrameSampleEstimates:
    """E2E tests for numpy PredictionFrame models (rangers)."""

    def test_red_ranger_single_origin_loads(self):
        """red_ranger PredictionFrame loads into a frame dict via loader."""
        manifest = _load_manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip(f"No predictions directory: {pf_dir}")

        frames = load_predictions(
            "prediction_frame",
            pf_dir / "origin_0",
            manifest["level"],
            manifest["targets"],
        )

        target = manifest["targets"][0]
        assert frames[target].sample_count == manifest["sample_size"]
        logger.info(
            f"red_ranger origin_0: {frames[target].n_rows} rows, "
            f"{frames[target].sample_count} samples"
        )

    def test_red_ranger_all_13_origins(self):
        """All 13 rolling origins load for red_ranger via loader."""
        manifest = _load_manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip(f"No predictions directory: {pf_dir}")

        target = manifest["targets"][0]
        for i in range(13):
            origin_dir = pf_dir / f"origin_{i}"
            if not origin_dir.exists():
                pytest.fail(f"Missing origin_{i}")
            frames = load_predictions(
                "prediction_frame",
                origin_dir,
                manifest["level"],
                manifest["targets"],
            )
            assert frames[target].sample_count == 256

    def test_red_ranger_calculate_map(self):
        """MAP computation works on real red_ranger samples loaded via loader."""
        manifest = _load_manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip(f"No predictions directory: {pf_dir}")

        frames = load_predictions(
            "prediction_frame",
            pf_dir / "origin_0",
            manifest["level"],
            manifest["targets"],
        )

        target = manifest["targets"][0]
        target_col = f"pred_{target}"
        map_df = calculate_map_frame(frames[target], target_col)
        map_col = f"{target_col}_map"

        assert map_col in map_df.columns
        assert not map_df[map_col].isna().all()
        assert len(map_df) == frames[target].n_rows
        logger.info(
            f"MAP range: [{map_df[map_col].min():.4f}, {map_df[map_col].max():.4f}]"
        )

    @patch("views_reporting.reports.report.PipelineConfig")
    def test_red_ranger_full_forecast_report(self, mock_config, tmp_path):
        """Full forecast report from red_ranger real PredictionFrame data via loader."""
        from views_reporting.templates.reports.forecast import ForecastReportTemplate

        manifest = _load_manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip(f"No predictions directory: {pf_dir}")

        historical_df = _load_historical(FIXTURE_DIR / "red_ranger")

        mock_config.current_version = "0.0.0-fixture-test"

        mock_model_path = MagicMock()
        mock_model_path.target = "model"
        mock_model_path.model_name = "red_ranger"
        mock_model_path.reports = tmp_path

        config = {
            "name": "red_ranger",
            "level": "cm",
            "targets": manifest["targets"],
        }

        with patch(
            "views_reporting.templates.reports.forecast.generate_model_file_name",
            return_value="red_ranger_fixture",
        ):
            for p in _patch_metadata():
                p.start()
            try:
                template = ForecastReportTemplate(
                    config=config,
                    model_path=mock_model_path,
                    run_type="calibration",
                )
                report_path = template.generate(
                    prediction_format="prediction_frame",
                    prediction_path=pf_dir / "origin_0",
                    historical_dataframe=historical_df,
                )
            finally:
                patch.stopall()

        assert report_path.exists()
        html = report_path.read_text()
        assert "<!DOCTYPE html>" in html
        assert "red_ranger" in html
        assert len(html) > 10000, f"Report too small ({len(html)} bytes)"
        logger.info(f"red_ranger report: {len(html)} bytes at {report_path}")


# ── Template loader-path integration (ADR-012) ──────────────────────────


@pytest.mark.slow
class TestTemplateLoaderPath:
    """Tests for ForecastReportTemplate.generate() with prediction_path."""

    @patch("views_reporting.reports.report.PipelineConfig")
    def test_forecast_via_prediction_path(self, mock_config, tmp_path):
        """Template generates report when given prediction_path instead of DataFrame."""
        from views_reporting.templates.reports.forecast import ForecastReportTemplate

        manifest = _load_manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip(f"No predictions directory: {pf_dir}")

        historical_df = _load_historical(FIXTURE_DIR / "red_ranger")

        mock_config.current_version = "0.0.0-path-test"

        mock_model_path = MagicMock()
        mock_model_path.target = "model"
        mock_model_path.model_name = "red_ranger"
        mock_model_path.reports = tmp_path

        config = {
            "name": "red_ranger",
            "level": "cm",
            "targets": manifest["targets"],
        }

        with patch(
            "views_reporting.templates.reports.forecast.generate_model_file_name",
            return_value="red_ranger_path_test",
        ):
            for p in _patch_metadata():
                p.start()
            try:
                template = ForecastReportTemplate(
                    config=config,
                    model_path=mock_model_path,
                    run_type="calibration",
                )
                report_path = template.generate(
                    prediction_format="prediction_frame",
                    prediction_path=pf_dir / "origin_0",
                    historical_dataframe=historical_df,
                )
            finally:
                patch.stopall()

        assert report_path.exists()
        html = report_path.read_text()
        assert "<!DOCTYPE html>" in html
        assert len(html) > 10000

    def test_forecast_both_inputs_raises(self, tmp_path):
        """Providing both forecast_dataframe and prediction_path raises."""
        from views_reporting.templates.reports.forecast import ForecastReportTemplate

        template = ForecastReportTemplate(
            config={"level": "cm", "targets": ["t"]},
            model_path=MagicMock(),
            run_type="calibration",
        )
        with pytest.raises(ValueError, match="not both"):
            template.generate(
                forecast_dataframe=pd.DataFrame(),
                prediction_path=tmp_path,
                prediction_format="dataframe",
            )

    def test_forecast_neither_input_raises(self):
        """Providing neither forecast_dataframe nor prediction_path raises."""
        from views_reporting.templates.reports.forecast import ForecastReportTemplate

        template = ForecastReportTemplate(
            config={"level": "cm", "targets": ["t"]},
            model_path=MagicMock(),
            run_type="calibration",
        )
        with pytest.raises(ValueError, match="Provide either"):
            template.generate()

    def test_prediction_path_without_format_raises(self, tmp_path):
        """prediction_path without prediction_format raises."""
        from views_reporting.templates.reports.forecast import ForecastReportTemplate

        template = ForecastReportTemplate(
            config={"level": "cm", "targets": ["t"]},
            model_path=MagicMock(),
            run_type="calibration",
        )
        with pytest.raises(ValueError, match="prediction_format is required"):
            template.generate(prediction_path=tmp_path)
