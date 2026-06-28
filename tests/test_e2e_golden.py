"""
Golden-file end-to-end tests using real prediction data.

These tests run the full reporting pipeline against actual model outputs
from views-models. They skip gracefully when the prediction files are
not present (CI, other developers' machines).

Data expectations:
- views-models lives at ../../views-models relative to this repo
- Models have prediction parquets in data/generated/
- Models have raw viewser DataFrames in data/raw/
"""

import glob
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from tests.conftest import cm_frame_from_df, mock_isoab_for_index, mock_name_for_index
from views_reporting.statistics import calculate_map_frame


def _patch_metadata():
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

logger = logging.getLogger(__name__)

try:
    from views_pipeline_core.data.handlers import CMDataset
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)

PLATFORM_ROOT = Path(__file__).resolve().parent.parent.parent
VIEWS_MODELS = PLATFORM_ROOT / "views-models"

# ── Golden data discovery ────────────────────────────────────────────────

GOLDEN_MODELS = {
    "brown_cheese": {
        "level": "cm",
        "target": "lr_ged_sb",
        "path": VIEWS_MODELS / "models" / "brown_cheese",
    },
    "locf_cmbaseline": {
        "level": "cm",
        "target": "lr_ged_sb",
        "path": VIEWS_MODELS / "models" / "locf_cmbaseline",
    },
}


def _discover_prediction_files(model_path, run_type="calibration"):
    """Find prediction sample files for a given model and run type."""
    pattern = str(model_path / "data" / "generated" / f"predictions_{run_type}_*_00.parquet")
    first_files = glob.glob(pattern)
    if not first_files:
        return None, None

    latest = sorted(first_files)[-1]
    prefix = latest.rsplit("_00.parquet", 1)[0]
    sample_files = sorted(glob.glob(f"{prefix}_*.parquet"))
    return latest, sample_files


def _assemble_samples(sample_files, target_col):
    """Assemble individual sample files into a single array-valued DataFrame."""
    dfs = [pd.read_parquet(f) for f in sample_files]
    base = dfs[0].copy()

    stacked = np.stack([df[target_col].values for df in dfs], axis=-1).astype(np.float32)

    base[target_col] = [stacked[i] for i in range(len(base))]
    return base


def _find_historical(model_path, run_type="calibration"):
    """Find the raw viewser DataFrame for historical data."""
    raw_path = model_path / "data" / "raw" / f"{run_type}_viewser_df.parquet"
    if raw_path.exists():
        return raw_path
    return None


def _require_golden_model(model_name, run_type="calibration"):
    """Return (prediction_df, historical_df, config) or skip."""
    if model_name not in GOLDEN_MODELS:
        pytest.skip(f"Unknown golden model: {model_name}")

    spec = GOLDEN_MODELS[model_name]
    model_path = spec["path"]

    if not model_path.exists():
        pytest.skip(f"Model directory not found: {model_path}")

    _, sample_files = _discover_prediction_files(model_path, run_type)
    if not sample_files:
        pytest.skip(f"No {run_type} prediction files for {model_name}")

    target_col = f"pred_{spec['target']}"
    prediction_df = _assemble_samples(sample_files, target_col)

    hist_path = _find_historical(model_path, run_type)
    historical_df = pd.read_parquet(hist_path) if hist_path else None

    config = {
        "name": model_name,
        "level": spec["level"],
        "targets": [spec["target"]],
    }

    logger.info(
        f"Golden model {model_name}: {len(sample_files)} samples, "
        f"{len(prediction_df)} rows, target={target_col}"
    )

    return prediction_df, historical_df, config


# ── Golden E2E: statistics on real data ──────────────────────────────────


@pytest.mark.slow
class TestGoldenStatistics:
    """MAP/HDI computation on real prediction data."""

    @pytest.mark.parametrize("model_name", list(GOLDEN_MODELS.keys()))
    def test_calculate_map_on_real_predictions(self, model_name):
        """calculate_map() produces valid results on real model output."""
        prediction_df, _, config = _require_golden_model(model_name)
        target_col = f"pred_{config['targets'][0]}"

        dataset = CMDataset(prediction_df)

        assert dataset.sample_size > 1, (
            f"Expected multi-sample predictions, got sample_size={dataset.sample_size}"
        )

        frame = cm_frame_from_df(prediction_df, config["targets"][0])
        map_df = calculate_map_frame(frame, target_col)
        map_col = f"{target_col}_map"

        assert map_col in map_df.columns
        assert not map_df[map_col].isna().all(), "All MAP values are NaN"
        assert map_df[map_col].dtype in (np.float32, np.float64)
        assert len(map_df) == len(prediction_df)

        non_negative = (map_df[map_col] >= 0).all()
        logger.info(
            f"{model_name}: MAP range [{map_df[map_col].min():.4f}, "
            f"{map_df[map_col].max():.4f}], all non-negative={non_negative}"
        )


# ── Golden E2E: full forecast report ─────────────────────────────────────


@pytest.mark.slow
class TestGoldenForecastReport:
    """Full ForecastReportTemplate pipeline on real data."""

    @patch("views_reporting.reports.report.PipelineConfig")
    @pytest.mark.parametrize("model_name", list(GOLDEN_MODELS.keys()))
    def test_full_report_pipeline(self, mock_config, model_name, tmp_path):
        """Full report pipeline produces valid HTML from real predictions."""
        from views_reporting.templates.reports.forecast import ForecastReportTemplate

        prediction_df, historical_df, config = _require_golden_model(model_name)

        mock_config.current_version = "0.0.0-golden-test"

        mock_model_path = MagicMock()
        mock_model_path.target = "model"
        mock_model_path.model_name = model_name
        mock_model_path.reports = tmp_path

        with patch(
            "views_reporting.templates.reports.forecast.generate_model_file_name",
            return_value=f"{model_name}_golden_test",
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
                    forecast_dataframe=prediction_df,
                    historical_dataframe=historical_df,
                )
            finally:
                patch.stopall()

        assert report_path.exists(), f"Report not created at {report_path}"
        html = report_path.read_text()
        assert "<!DOCTYPE html>" in html
        assert model_name in html
        assert len(html) > 5000, f"Report too small ({len(html)} bytes)"

        logger.info(
            f"{model_name}: golden report generated, {len(html)} bytes at {report_path}"
        )


# ── Golden E2E: report content validation ────────────────────────────────


@pytest.mark.slow
class TestGoldenReportContent:
    """Structural validation of reports generated from real data."""

    @patch("views_reporting.reports.report.PipelineConfig")
    def test_report_contains_map_and_graph(self, mock_config, tmp_path):
        """Golden report contains both map visualizations and line graphs."""
        from views_reporting.templates.reports.forecast import ForecastReportTemplate

        prediction_df, historical_df, config = _require_golden_model("brown_cheese")

        mock_config.current_version = "0.0.0-golden-test"

        mock_model_path = MagicMock()
        mock_model_path.target = "model"
        mock_model_path.model_name = "brown_cheese"
        mock_model_path.reports = tmp_path

        with patch(
            "views_reporting.templates.reports.forecast.generate_model_file_name",
            return_value="golden_content_test",
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
                    forecast_dataframe=prediction_df,
                    historical_dataframe=historical_df,
                )
            finally:
                patch.stopall()

        html = report_path.read_text()
        assert "plotly" in html.lower(), "No Plotly content in report"
        assert "<h1" in html, "No h1 heading in report"
        assert "<h2" in html, "No h2 heading (Maps section) in report"
        assert "iframe" in html or "div" in html.lower(), "No embedded viz"
