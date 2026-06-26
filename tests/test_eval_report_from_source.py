"""Offline evaluation-report tests driven through the injected EvaluationSource
(#173 / C-108) — no WandB, no pipeline-core producer. The wandb-free replacement for
the metric assertions in test_e2e_eval_report.py.

Covers: sections render; one canonical table per active cell; "not calculated" note for
a missing canonical metric; visible "ambiguous" cell (C-116); absent / degraded
constituent degrade-and-announce (#105/#177); strict_constituents → raise; and the
cross-constituent level/partition consistency guard (C-48).
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
from _wandb_doubles import FakeWandbRun  # noqa: E402

from views_reporting.sources import WandbEvaluationSource, mean_metric_value  # noqa: E402

TARGET = "lr_ged_sb"


def _model_path(reports_dir: Path, *, target: str, model_name: str) -> MagicMock:
    mp = MagicMock()
    mp.target = target
    mp.model_name = model_name
    mp.reports = reports_dir
    # Sample-graph discovery finds nothing → a visible "unavailable" note (non-fatal).
    mp._get_generated_predictions_data_file_paths.return_value = []
    return mp


def _config(models=None) -> dict:
    return {
        "name": "subject",
        "level": "cm",
        "prediction_format": "dataframe",
        "targets": [TARGET],
        "regression_point_metrics": ["MSLE"],  # → (regression, point) cell active
        "models": models or [],
    }


def _template(tmp_path, *, target, model_name, models=None):
    return EvaluationReportTemplate(
        _config(models=models), _model_path(tmp_path, target=target, model_name=model_name),
        run_type="calibration",
    )


@pytest.mark.beige_team
def test_single_model_renders_from_source(tmp_path):
    src = FakeEvaluationSource(
        {"red_ranger": make_metric_frame({"MSLE": 0.42}, target=TARGET)}
    )
    template = _template(tmp_path, target="model", model_name="red_ranger")
    html = Path(template.generate(source=src, target=TARGET)).read_text()

    for section in ("Run Summary", "Task Description", "Model Metrics"):
        assert section in html
    assert "Regression (point)" in html
    assert "red_ranger" in html
    assert "fake-run" in html  # provenance run_id rendered
    # MSLE present; the other canonical reg-point metrics absent from the frame →
    # the explicit "not calculated" note naming the config key.
    assert "not calculated" in html.lower()


@pytest.mark.beige_team
def test_ensemble_subject_and_constituents(tmp_path):
    src = FakeEvaluationSource(
        {
            "first_love": make_metric_frame({"MSLE": 0.40}, target=TARGET),
            "red_ranger": make_metric_frame({"MSLE": 0.51}, target=TARGET),
            "blue_ranger": make_metric_frame({"MSLE": 0.55}, target=TARGET),
        }
    )
    template = _template(
        tmp_path, target="ensemble", model_name="first_love",
        models=["red_ranger", "blue_ranger"],
    )
    html = Path(template.generate(source=src, target=TARGET)).read_text()
    for name in ("first_love", "red_ranger", "blue_ranger"):
        assert name in html


@pytest.mark.red_team
def test_ambiguous_metric_renders_ambiguous(tmp_path):
    # C-116: a frame with two mean rows for MSLE → visible "ambiguous", not a number.
    colliding = make_metric_frame(
        {"MSLE": 0.51}, target=TARGET, extra_rows=[("MSLE", 0.99)]
    )
    src = FakeEvaluationSource({"red_ranger": colliding})
    template = _template(tmp_path, target="model", model_name="red_ranger")
    html = Path(template.generate(source=src, target=TARGET)).read_text()
    assert "ambiguous" in html.lower()
    assert "0.99" not in html and "0.51" not in html  # neither number silently picked


@pytest.mark.red_team
def test_absent_constituent_is_announced(tmp_path):
    src = FakeEvaluationSource(
        {
            "first_love": make_metric_frame({"MSLE": 0.40}, target=TARGET),
            "red_ranger": None,  # absent
        }
    )
    template = _template(
        tmp_path, target="ensemble", model_name="first_love", models=["red_ranger"]
    )
    html = Path(template.generate(source=src, target=TARGET)).read_text()
    assert "absent" in html.lower()
    assert "red_ranger" in html


@pytest.mark.red_team
def test_transient_constituent_is_degraded(tmp_path):
    src = FakeEvaluationSource(
        {
            "first_love": make_metric_frame({"MSLE": 0.40}, target=TARGET),
            "red_ranger": RuntimeError("network hiccup"),  # raises → degraded
        }
    )
    template = _template(
        tmp_path, target="ensemble", model_name="first_love", models=["red_ranger"]
    )
    html = Path(template.generate(source=src, target=TARGET)).read_text()
    assert "degraded" in html.lower()


@pytest.mark.red_team
def test_strict_constituents_raises_on_absent(tmp_path):
    src = FakeEvaluationSource(
        {"first_love": make_metric_frame({"MSLE": 0.40}, target=TARGET), "red_ranger": None}
    )
    template = _template(
        tmp_path, target="ensemble", model_name="first_love", models=["red_ranger"]
    )
    template.config["strict_constituents"] = True
    with pytest.raises(ValueError, match="strict_constituents"):
        template.generate(source=src, target=TARGET)


@pytest.mark.red_team
def test_constituent_level_mismatch_raises(tmp_path):
    src = FakeEvaluationSource(
        {
            "first_love": make_metric_frame({"MSLE": 0.40}, target=TARGET, level="cm"),
            "red_ranger": make_metric_frame({"MSLE": 0.51}, target=TARGET, level="cm"),
            "blue_ranger": make_metric_frame({"MSLE": 0.55}, target=TARGET, level="pgm"),
        }
    )
    template = _template(
        tmp_path, target="ensemble", model_name="first_love",
        models=["red_ranger", "blue_ranger"],
    )
    with pytest.raises(ValueError, match="level"):
        template.generate(source=src, target=TARGET)


@pytest.mark.green_team
def test_wandb_source_skips_non_numeric_value():
    # A None/non-numeric summary value must not crash frame construction; it is
    # omitted (renders "not calculated") while numeric metrics still come through.
    run = FakeWandbRun(
        summary={
            f"time-series-wise_MSLE_mean_{TARGET}_best": None,  # non-numeric
            f"time-series-wise_MSE_mean_{TARGET}_best": 12.7,
        },
        config={"name": "red_ranger", "level": "cm"},
    )
    src = WandbEvaluationSource(
        run, run_type="calibration", config={"regression_point_metrics": ["MSLE"]},
        target=TARGET, primary_model="red_ranger", eval_types=["time-series-wise"],
    )
    frame = src.metric_frame("red_ranger")  # must not raise
    et = "time-series-wise"
    msle = mean_metric_value(frame, eval_type=et, target=TARGET, metric="MSLE")
    mse = mean_metric_value(frame, eval_type=et, target=TARGET, metric="MSE")
    assert msle is None
    assert mse == pytest.approx(12.7)


@pytest.mark.red_team
def test_subject_level_mismatch_with_constituents_raises(tmp_path):
    # The SUBJECT must be in the consistency baseline (the old check seeded its level
    # from the subject): a subject at pgm with constituents at cm must raise, not pass.
    src = FakeEvaluationSource(
        {
            "first_love": make_metric_frame({"MSLE": 0.40}, target=TARGET, level="pgm"),
            "red_ranger": make_metric_frame({"MSLE": 0.51}, target=TARGET, level="cm"),
        }
    )
    template = _template(
        tmp_path, target="ensemble", model_name="first_love", models=["red_ranger"]
    )
    with pytest.raises(ValueError, match="level"):
        template.generate(source=src, target=TARGET)
