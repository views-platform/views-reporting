"""Offline end-to-end evaluation-report tests — driven through the injected
EvaluationSource (the durable path; the WandB scrape is gone, C-108 B2).

Renders the FULL evaluation report (Run Summary, Task Description, Model Metrics,
Prediction Samples) from synthetic MetricFrames — no WandB. Guards that "the current
setup can produce evaluation reports like the real artifact", including the 90/95/99
HDI legend selector and the hindcast caption (the sample-graph coverage unique to this
file; behaviour invariants live in test_eval_report_from_source.py).
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
from _eval_source_doubles import FakeEvaluationSource, make_metric_frame  # noqa: E402

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


def _frame(metrics: dict, **kw):
    return make_metric_frame(metrics, target=TARGET, **kw)


@pytest.mark.beige_team
@pytest.mark.slow
def test_single_model_eval_report_offline(tmp_path):
    """A single-model eval report renders fully offline from a MetricFrame and
    includes the HDI legend selector in its prediction sample graphs."""
    # The HDI sample graphs need the real PredictionFrame fixtures, which are
    # gitignored (absent on CI / fresh clones). Skip rather than fail, per the
    # repo's fixture contract (see tests/data/README.md, test_e2e_fixture.py).
    if not (FIX / "predictions_calibration").exists():
        pytest.skip(f"prediction fixtures absent: {FIX / 'predictions_calibration'}")
    template = EvaluationReportTemplate(
        _config(), _model_path_double(tmp_path, target="model"), run_type="calibration"
    )
    # red_ranger carries MSLE (reg-point) + CRPS (reg-sample); the other canonical
    # metrics are absent → "not calculated".
    source = FakeEvaluationSource(
        {"red_ranger": _frame({"MSLE": 0.42, "CRPS": 0.88})}
    )
    path = template.generate(source=source, target=TARGET)
    html = Path(path).read_text()

    for section in ("Run Summary", "Task Description", "Model Metrics", "Prediction Samples"):
        assert section in html, f"missing section: {section}"
    assert "MSLE" in html, "expected a rendered metric in the Model Metrics table"
    for pct in ("90% HDI", "95% HDI", "99% HDI"):
        assert pct in html, f"missing HDI level in sample graphs: {pct}"
    assert "hindcast" in html.lower(), "calibration rolling-origins should be hindcast-annotated"
    # canonical per-cell tables (config marks regression point + sample active)
    assert "Regression (point)" in html and "Regression (sample)" in html
    # canonical reg-sample = (CRPS, QS_sample, MCR_sample); frame has only CRPS →
    # the others render the explicit "not calculated" note
    assert "not calculated" in html.lower()


@pytest.mark.beige_team
@pytest.mark.slow
def test_ensemble_eval_report_offline(tmp_path):
    """An ensemble eval report renders offline from per-model MetricFrames: Run
    Summary lists constituents, Model Metrics concatenates ensemble + constituent
    rows, and the Prediction-Samples section is VISIBLY noted unavailable (C-40)
    since no predictions are on disk."""
    model_path = _model_path_double(tmp_path, target="ensemble")
    model_path.model_name = "first_love"
    model_path._get_generated_pf_prediction_paths.return_value = []  # samples → C-40 note
    config = _config(models=["red_ranger", "blue_ranger"])
    config["name"] = "first_love"

    source = FakeEvaluationSource(
        {
            "first_love": _frame({"MSLE": 0.40, "CRPS": 0.85}),
            "red_ranger": _frame({"MSLE": 0.51, "CRPS": 0.93}),
            "blue_ranger": _frame({"MSLE": 0.55, "CRPS": 0.95}),
        }
    )
    template = EvaluationReportTemplate(config, model_path, run_type="calibration")
    html = Path(template.generate(source=source, target=TARGET)).read_text()

    assert "Run Summary" in html and "Constituent Models" in html
    assert "Model Metrics" in html
    for name in ("first_love", "red_ranger", "blue_ranger"):
        assert name in html, f"expected {name} as a metric-table row"
    # C-40: samples section present and visibly noted unavailable
    assert "Prediction Samples" in html
    assert "unavailable" in html.lower()
    assert "Regression (point)" in html and "Regression (sample)" in html
    # C-34 provenance footer: build stamp + the run identity from the frame source
    assert "views-reporting v" in html and "views-frames v" in html
    assert "fake-run" in html  # provenance run_id (FakeEvaluationSource default)


@pytest.mark.green_team
def test_canonical_multicell_tables_and_missing_note(tmp_path):
    """ADR-017: one canonical table per active cell (from the config's `*_metrics`
    keys), drawing the metric SET from the central ReportingConfig — not the model's
    list — and noting canonical metrics the frame lacks, naming the exact config key."""
    model_path = MagicMock()
    model_path.target = "model"
    model_path.model_name = "m1"
    model_path.reports = tmp_path
    model_path._get_generated_pf_prediction_paths.return_value = []  # samples → note
    config = {
        "level": "cm",
        "prediction_format": "prediction_frame",
        "regression_point_metrics": ["MSLE"],       # → regression/point cell active
        "classification_point_metrics": ["Brier_cls"],  # → classification/point active
        "models": [],
    }
    template = EvaluationReportTemplate(config, model_path, run_type="calibration")
    # frame carries the reg-point MSLE only; other reg-point + all class-point absent.
    source = FakeEvaluationSource({"m1": _frame({"MSLE": 0.42})})
    html = Path(template.generate(source=source, target=TARGET)).read_text()

    assert "Regression (point)" in html and "Classification (point)" in html
    assert "MSLE" in html and "Brier_cls" in html  # canonical metrics attempted
    # MAE (canonical reg-point) and Brier_cls (canonical class-point) absent from frame
    assert "not calculated" in html.lower()
    assert "classification_point_metrics" in html  # the exact key named in the note
