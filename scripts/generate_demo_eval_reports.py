#!/usr/bin/env python
"""Generate full EVALUATION reports **offline** for human inspection, driving the
**durable** path: synthetic ``MetricFrame``s persisted to a temp dir and read back
through a real ``MetricFrameFileSource`` — exactly as pipeline-core's reporting stage
feeds the report (ADR-018 / C-108). No WandB. Produces:

  * a single-model report (red_ranger) — real prediction data drives the HDI
    sample graphs; metric values come from a synthetic MetricFrame;
  * an ensemble report (first_love) — constituent + baseline metric rows from
    per-model MetricFrames, exercising the multi-row Model-Metrics table.

Both render the **canonical** metric standard (ADR-017) per active cell.

HONESTY: metric VALUES are synthetic/illustrative (there is no recorded real
evaluation in the repo — only real *predictions*). The report structure, the
durable source path, and the sample graphs are real. For real metric values, run
the pipeline `--evaluate --report`.

    uv run python scripts/generate_demo_eval_reports.py
Outputs (gitignored): demo_reports/evaluation_red_ranger_fresh.html,
                      demo_reports/evaluation_ensemble_first_love_fresh.html
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("generate_demo_eval_reports")

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "tests" / "data" / "red_ranger"
OUT = REPO / "demo_reports"
sys.path.insert(0, str(REPO / "tests"))  # reuse the test-only MetricFrame builder

from _eval_source_doubles import make_metric_frame  # noqa: E402

TARGET = "lr_ged_sb"
RUN_TYPE = "calibration"
_BASE = {"MSLE": 0.42, "MSE": 12.7, "MCR_point": 0.92, "y_hat_bar": 21.3,
         "CRPS": 0.87, "MIS": 320.0, "Ignorance": 1.21, "MCR_sample": 0.86}


def _best_effort_version_stamp() -> None:
    from views_pipeline_core.configs.pipeline import PipelineConfig
    try:
        if not getattr(PipelineConfig, "current_version", None):
            PipelineConfig.current_version = "0.1.0-demo"
    except AttributeError:
        pass  # newer pipeline-core: current_version is read-only


def _model_path(model_name: str, target: str, with_samples: bool) -> MagicMock:
    mp = MagicMock()
    mp.target = target
    mp.model_name = model_name
    mp.reports = OUT
    mp._get_raw_data_file_paths.return_value = [FIX / "calibration_viewser_df.parquet"]
    mp._get_generated_pf_prediction_paths.return_value = (
        [FIX / "predictions_calibration"] if with_samples else []
    )
    return mp


def _frame(model: str, i: int):
    """A MetricFrame carrying the canonical regression metrics (point + sample),
    values offset per ``i`` so per-model rows differ, with demo provenance attached."""
    from views_evaluation.evaluation.metric_frame import MetricFrameMetadata
    from views_frames.metadata import FrameMetadata

    values = {m: round(base * (1 + 0.12 * i), 6) for m, base in _BASE.items()}
    base = make_metric_frame(values, target=TARGET)
    metadata = MetricFrameMetadata(
        provenance=FrameMetadata(
            model=model,
            run_type=RUN_TYPE,
            run_id=f"demo-{model}",
            data_version="demo-data-v0",
        ),
        scoring_code_version="demo-eval-v0",
        evaluation_timestamp="2026-06-27T00:00:00Z",
    )
    return type(base)(values=base.values, identifiers=base.identifiers, metadata=metadata)


def _persist(root: Path, model: str, i: int) -> None:
    """Save a model's synthetic MetricFrame to the MetricFrameFileSource layout."""
    _frame(model, i).save(root / model / RUN_TYPE / f"metricframe_{TARGET}")


def _file_source(root: Path, primary_model: str):
    from views_reporting.sources import MetricFrameFileSource

    return MetricFrameFileSource(
        root=root, run_type=RUN_TYPE, target=TARGET, primary_model=primary_model
    )


def _reg_cells_config(name: str, **extra) -> dict:
    from views_reporting.config import get_config
    cfg = get_config()
    return {
        "name": name, "level": "cm", "prediction_format": "prediction_frame",
        "targets": [TARGET],
        "regression_point_metrics": list(cfg.canonical_metrics("regression", "point")),
        "regression_sample_metrics": list(cfg.canonical_metrics("regression", "sample")),
        **extra,
    }


def generate_single_model(root: Path) -> Path:
    from views_reporting.templates.reports.evaluation import EvaluationReportTemplate

    _persist(root, "red_ranger", i=0)
    mp = _model_path("red_ranger", target="model", with_samples=True)
    config = _reg_cells_config("red_ranger", models=[])
    produced = EvaluationReportTemplate(config, mp, run_type=RUN_TYPE).generate(
        source=_file_source(root, "red_ranger"), target=TARGET
    )
    return _move(produced, "evaluation_red_ranger_fresh.html")


def generate_ensemble(root: Path) -> Path:
    from views_reporting.templates.reports.evaluation import EvaluationReportTemplate

    constituents = ["bad_romance", "free_fallin", "cold_heart", "beautiful_people"]
    baselines = ["maroon_ranger", "red_ranger"]
    _persist(root, "first_love", i=0)
    for i, model in enumerate(constituents + baselines):
        _persist(root, model, i=i + 1)

    # Demo-only shim: the ensemble sample-graphs path builds a
    # ModelPathManager(constituent[0]) for historical data. Point it at the
    # red_ranger fixtures so the HDI graphs render offline. (Dev script only.)
    import views_pipeline_core.data.model_path as mpm_mod

    class _DemoMPM:
        def __init__(self, *a, **k):
            pass

        def _get_raw_data_file_paths(self, run_type):
            return [FIX / "calibration_viewser_df.parquet"]

    mpm_mod.ModelPathManager = _DemoMPM

    mp = _model_path("first_love", target="ensemble", with_samples=True)
    config = _reg_cells_config(
        "first_love", models=constituents, regression_sample_baselines=baselines
    )
    produced = EvaluationReportTemplate(config, mp, run_type=RUN_TYPE).generate(
        source=_file_source(root, "first_love"), target=TARGET
    )
    return _move(produced, "evaluation_ensemble_first_love_fresh.html")


def _move(produced: Path, name: str) -> Path:
    friendly = OUT / name
    if Path(produced).resolve() != friendly.resolve():
        Path(produced).replace(friendly)
    log.info("  -> %s (%.1f MB)", friendly, friendly.stat().st_size / 1e6)
    return friendly


def main() -> None:
    OUT.mkdir(exist_ok=True)
    _best_effort_version_stamp()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        results = [generate_single_model(root), generate_ensemble(root)]
    print("\n=== offline evaluation reports (synthetic metric values; graphs real) ===")
    for p in results:
        print(f"  ✓ file://{p}  ({p.stat().st_size / 1e6:.1f} MB)")
    print("  For real metric values, run the pipeline `--evaluate --report`.")


if __name__ == "__main__":
    main()
