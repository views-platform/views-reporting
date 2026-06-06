"""Offline end-to-end evaluation-report tests.

Renders the FULL evaluation report (Run Summary, Task Description, Model Metrics,
Prediction Samples) from the repo alone, via a synthetic WandB-run double — no
live WandB. Guards that "the current setup can produce evaluation reports like the
real artifact", including the 90/95/99 HDI legend selector and the hindcast
caption. Metric values are illustrative (see tests/_wandb_doubles.py).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

try:
    from views_pipeline_core.data.handlers import CMDataset  # noqa: F401

    from views_reporting.templates.reports.evaluation import EvaluationReportTemplate
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).parent))
from _wandb_doubles import (  # noqa: E402
    FakeWandbRun,
    load_fake_run,
    make_get_latest_run,
)

FIX = Path(__file__).parent / "data" / "red_ranger"
TARGET = "lr_ged_sb"


def _model_path_double(reports_dir: Path, target: str = "model") -> MagicMock:
    mp = MagicMock()
    mp.target = target
    mp.model_name = "red_ranger"
    mp.reports = reports_dir
    mp._get_raw_data_file_paths.return_value = [FIX / "calibration_viewser_df.parquet"]
    mp._get_generated_pf_prediction_paths.return_value = [FIX / "predictions_calibration"]
    return mp


def _config(models=None) -> dict:
    return {
        "name": "red_ranger",
        "level": "cm",
        "prediction_format": "prediction_frame",
        "targets": [TARGET],
        "regression_point_metrics": ["MSLE", "MAE"],
        "regression_sample_metrics": ["CRPS"],
        "models": models or [],
    }


@pytest.mark.beige_team
@pytest.mark.slow
def test_single_model_eval_report_offline(tmp_path):
    """A single-model eval report renders fully offline (no get_latest_run calls)
    and includes the HDI legend selector in its prediction sample graphs."""
    template = EvaluationReportTemplate(
        _config(), _model_path_double(tmp_path, target="model"), run_type="calibration"
    )
    path = template.generate(load_fake_run(FIX / "wandb_run.json"), TARGET)
    html = Path(path).read_text()

    for section in ("Run Summary", "Task Description", "Model Metrics", "Prediction Samples"):
        assert section in html, f"missing section: {section}"
    assert "MSLE" in html, "expected a rendered metric in the Model Metrics table"
    for pct in ("90% HDI", "95% HDI", "99% HDI"):
        assert pct in html, f"missing HDI level in sample graphs: {pct}"
    assert "hindcast" in html.lower(), "calibration rolling-origins should be hindcast-annotated"


def _constituent_run(name: str) -> FakeWandbRun:
    return FakeWandbRun(
        summary={
            "_timestamp": 1717560000,
            "runtime": 1800,
            f"time-series-wise_MSLE_mean_{TARGET}_best": 0.51,
            f"time-series-wise_MAE_mean_{TARGET}_best": 1.20,
            f"time-series-wise_CRPS_mean_{TARGET}_best": 0.93,
        },
        config={
            "name": name,
            "level": "cm",
            "steps": [1, 36],
            "eval_type": "standard",
            "calibration": {"train": [121, 444], "test": [445, 492]},
        },
    )


@pytest.mark.beige_team
@pytest.mark.slow
def test_ensemble_eval_report_offline(tmp_path, monkeypatch):
    """An ensemble eval report renders offline with constituent runs supplied via
    a mocked get_latest_run: Run Summary lists constituents, Model Metrics
    concatenates ensemble + constituent rows, and the Prediction-Samples section
    is VISIBLY noted unavailable (C-40) since no constituent raw data is on disk."""
    import views_reporting.templates.reports.evaluation as evalmod

    monkeypatch.setattr(
        evalmod,
        "get_latest_run",
        make_get_latest_run(
            {
                "red_ranger": _constituent_run("red_ranger"),
                "blue_ranger": _constituent_run("blue_ranger"),
            }
        ),
    )
    # The ensemble sample-graphs path builds a ModelPathManager(constituent[0])
    # for historical data — stub it to have no raw data so we exercise the C-40
    # visible-note path without touching a real model directory.
    mp_cls = MagicMock()
    mp_cls.return_value._get_raw_data_file_paths.return_value = []
    monkeypatch.setattr(
        "views_pipeline_core.data.model_path.ModelPathManager", mp_cls
    )

    model_path = _model_path_double(tmp_path, target="ensemble")
    model_path.model_name = "first_love"
    config = _config(models=["red_ranger", "blue_ranger"])
    config["name"] = "first_love"

    template = EvaluationReportTemplate(config, model_path, run_type="calibration")
    ensemble_run = _constituent_run("first_love")
    ensemble_run.config["models"] = ["red_ranger", "blue_ranger"]

    html = Path(template.generate(ensemble_run, TARGET)).read_text()

    assert "Run Summary" in html and "Constituent Models" in html
    assert "Model Metrics" in html
    for name in ("first_love", "red_ranger", "blue_ranger"):
        assert name in html, f"expected {name} as a metric-table row"
    # C-40: samples section is present and visibly noted unavailable
    assert "Prediction Samples" in html
    assert "unavailable" in html.lower()
