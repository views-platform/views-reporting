"""
End-to-end tests using real fixture data from tests/data/.

Two formats tested:
1. Parquet → DataFrame (point estimates): average_cmbaseline, average_pgmbaseline
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
    from views_pipeline_core.data.handlers import CMDataset, PGMDataset
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)

from tests.conftest import mock_isoab_for_df, mock_name_for_df
from views_reporting.statistics import calculate_map

logger = logging.getLogger(__name__)

FIXTURE_DIR = Path(__file__).parent / "data"
DATASET_CLASSES = {"cm": CMDataset, "pgm": PGMDataset}


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


def _load_parquet_origin(path, level):
    """Load a single parquet origin into a Dataset."""
    df = pd.read_parquet(path)
    return DATASET_CLASSES[level](df)


def _load_pf_origin(origin_dir, target, level):
    """Load a single PredictionFrame origin into a Dataset."""
    from views_pipeline_core.data.prediction_frame import PredictionFrame
    from views_pipeline_core.managers.prediction.prediction_frame_converter import (
        PredictionFrameConverter,
    )

    target_dir = origin_dir / target
    if not (target_dir / "y_pred.npy").exists():
        pytest.skip(f"No y_pred.npy in {target_dir}")

    pf = PredictionFrame.load(target_dir)
    converter = PredictionFrameConverter()
    pred_df = converter.to_prediction_df(pf, target)

    index_names = {
        "cm": ["month_id", "country_id"],
        "pgm": ["month_id", "priogrid_id"],
    }
    pred_df.index = pred_df.index.set_names(index_names[level])
    return DATASET_CLASSES[level](pred_df)


def _load_historical(model_dir):
    """Load the historical viewser DataFrame."""
    hist_path = model_dir / "calibration_viewser_df.parquet"
    if not hist_path.exists():
        return None
    return pd.read_parquet(hist_path)


# ── Format 1: Parquet point estimates ────────────────────────────────────


@pytest.mark.slow
class TestParquetPointEstimates:
    """E2E tests for parquet DataFrame models (average baselines)."""

    @pytest.mark.parametrize("model_name", ["average_cmbaseline", "average_pgmbaseline"])
    def test_dataset_creation(self, model_name):
        """Parquet fixture loads into a valid Dataset."""
        manifest = _load_manifest(model_name)
        model_dir = FIXTURE_DIR / model_name
        origins = _discover_parquet_origins(model_dir, manifest)

        ds = _load_parquet_origin(origins[0], manifest["level"])

        assert ds.sample_size == 1
        assert ds.is_prediction
        assert f"pred_{manifest['targets'][0]}" in ds.targets

    @pytest.mark.parametrize("model_name", ["average_cmbaseline", "average_pgmbaseline"])
    def test_all_13_origins_load(self, model_name):
        """All 13 rolling origins load successfully."""
        manifest = _load_manifest(model_name)
        model_dir = FIXTURE_DIR / model_name
        origins = _discover_parquet_origins(model_dir, manifest)

        assert len(origins) == 13, f"Expected 13 origins, got {len(origins)}"
        for path in origins:
            ds = _load_parquet_origin(path, manifest["level"])
            assert ds.is_prediction

    @patch("views_reporting.mapping.mapping.get_name")
    @patch("views_reporting.mapping.mapping.get_isoab")
    @patch("views_reporting.reports.report.PipelineConfig")
    def test_cm_point_forecast_report(
        self, mock_config, mock_isoab, mock_name, tmp_path
    ):
        """Full forecast report from average_cmbaseline real data."""
        from views_reporting.templates.reports.forecast import ForecastReportTemplate

        manifest = _load_manifest("average_cmbaseline")
        model_dir = FIXTURE_DIR / "average_cmbaseline"
        origins = _discover_parquet_origins(model_dir, manifest)

        forecast_df = pd.read_parquet(origins[0])
        historical_df = _load_historical(model_dir)

        mock_config.current_version = "0.0.0-fixture-test"
        mock_isoab.side_effect = lambda ds: mock_isoab_for_df(
            ds.dataframe, ds._entity_id, ds._time_id
        )
        mock_name.side_effect = lambda ds, **kw: mock_name_for_df(
            ds.dataframe, ds._entity_id, ds._time_id
        )

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
            template = ForecastReportTemplate(
                config=config,
                model_path=mock_model_path,
                run_type="calibration",
            )
            report_path = template.generate(
                forecast_dataframe=forecast_df,
                historical_dataframe=historical_df,
            )

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
        """red_ranger PredictionFrame loads into a valid CMDataset."""
        manifest = _load_manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip(f"No predictions directory: {pf_dir}")

        ds = _load_pf_origin(
            pf_dir / "origin_0", manifest["targets"][0], manifest["level"]
        )

        assert ds.sample_size == manifest["sample_size"]
        assert ds.is_prediction
        assert f"pred_{manifest['targets'][0]}" in ds.targets
        logger.info(
            f"red_ranger origin_0: {ds.num_entities} entities, "
            f"{ds.num_time_steps} months, {ds.sample_size} samples"
        )

    def test_red_ranger_all_13_origins(self):
        """All 13 rolling origins load for red_ranger."""
        manifest = _load_manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip(f"No predictions directory: {pf_dir}")

        for i in range(13):
            origin_dir = pf_dir / f"origin_{i}"
            if not origin_dir.exists():
                pytest.fail(f"Missing origin_{i}")
            ds = _load_pf_origin(
                origin_dir, manifest["targets"][0], manifest["level"]
            )
            assert ds.is_prediction
            assert ds.sample_size == 256

    def test_red_ranger_calculate_map(self):
        """MAP computation works on real red_ranger samples."""
        manifest = _load_manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip(f"No predictions directory: {pf_dir}")

        ds = _load_pf_origin(
            pf_dir / "origin_0", manifest["targets"][0], manifest["level"]
        )

        target_col = f"pred_{manifest['targets'][0]}"
        map_df = calculate_map(ds, features=[target_col], alpha=0.9)
        map_col = f"{target_col}_map"

        assert map_col in map_df.columns
        assert not map_df[map_col].isna().all()
        assert len(map_df) == len(ds.dataframe)
        logger.info(
            f"MAP range: [{map_df[map_col].min():.4f}, {map_df[map_col].max():.4f}]"
        )

    @patch("views_reporting.mapping.mapping.get_name")
    @patch("views_reporting.mapping.mapping.get_isoab")
    @patch("views_reporting.reports.report.PipelineConfig")
    def test_red_ranger_full_forecast_report(
        self, mock_config, mock_isoab, mock_name, tmp_path
    ):
        """Full forecast report from red_ranger real PredictionFrame data."""
        from views_reporting.templates.reports.forecast import ForecastReportTemplate

        manifest = _load_manifest("red_ranger")
        pf_dir = FIXTURE_DIR / "red_ranger" / "predictions_calibration"
        if not pf_dir.exists():
            pytest.skip(f"No predictions directory: {pf_dir}")

        ds = _load_pf_origin(
            pf_dir / "origin_0", manifest["targets"][0], manifest["level"]
        )
        forecast_df = ds.dataframe
        historical_df = _load_historical(FIXTURE_DIR / "red_ranger")

        mock_config.current_version = "0.0.0-fixture-test"
        mock_isoab.side_effect = lambda ds: mock_isoab_for_df(
            ds.dataframe, ds._entity_id, ds._time_id
        )
        mock_name.side_effect = lambda ds, **kw: mock_name_for_df(
            ds.dataframe, ds._entity_id, ds._time_id
        )

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
            template = ForecastReportTemplate(
                config=config,
                model_path=mock_model_path,
                run_type="calibration",
            )
            report_path = template.generate(
                forecast_dataframe=forecast_df,
                historical_dataframe=historical_df,
            )

        assert report_path.exists()
        html = report_path.read_text()
        assert "<!DOCTYPE html>" in html
        assert "red_ranger" in html
        assert len(html) > 10000, f"Report too small ({len(html)} bytes)"
        logger.info(f"red_ranger report: {len(html)} bytes at {report_path}")
