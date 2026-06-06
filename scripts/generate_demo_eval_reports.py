#!/usr/bin/env python
"""Generate a full EVALUATION report **offline** for human inspection, using a
synthetic WandB-run double (no live WandB).

This complements `generate_demo_reports.py` (forecast reports). It drives the real
`EvaluationReportTemplate.generate()` end-to-end for the red_ranger CM sample
model, producing Run Summary + Task Description + Model Metrics + Prediction
Samples — the last carrying the legend-selectable 90/95/99% HDI bands.

HONESTY: the metric VALUES come from a synthetic run fixture
(`tests/data/red_ranger/wandb_run.json`) and are *illustrative*. The report
structure and the rendered graphs are real; the numbers are not from a real
evaluation. For a real evaluation report, use the pipeline (`--evaluate --report`).

    uv run python scripts/generate_demo_eval_reports.py
Output: demo_reports/evaluation_red_ranger_fresh.html  (gitignored)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("generate_demo_eval_reports")

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "tests" / "data" / "red_ranger"
OUT = REPO / "demo_reports"
sys.path.insert(0, str(REPO / "tests"))  # reuse the test-only WandB double

from _wandb_doubles import load_fake_run  # noqa: E402


def main() -> None:
    from views_pipeline_core.configs.pipeline import PipelineConfig

    from views_reporting.templates.reports.evaluation import EvaluationReportTemplate

    # Best-effort footer stamp (current_version is read-only on newer pipeline-core).
    try:
        if not getattr(PipelineConfig, "current_version", None):
            PipelineConfig.current_version = "0.1.0-demo"
    except AttributeError:
        pass

    OUT.mkdir(exist_ok=True)
    target = "lr_ged_sb"

    model_path = MagicMock()
    model_path.target = "model"
    model_path.model_name = "red_ranger"
    model_path.reports = OUT
    model_path._get_raw_data_file_paths.return_value = [
        FIX / "calibration_viewser_df.parquet"
    ]
    model_path._get_generated_pf_prediction_paths.return_value = [
        FIX / "predictions_calibration"
    ]

    config = {
        "name": "red_ranger",
        "level": "cm",
        "prediction_format": "prediction_frame",
        "targets": [target],
        "regression_point_metrics": ["MSLE", "MAE"],
        "regression_sample_metrics": ["CRPS"],
        "models": [],
    }

    template = EvaluationReportTemplate(config, model_path, run_type="calibration")
    produced = template.generate(load_fake_run(FIX / "wandb_run.json"), target)

    friendly = OUT / "evaluation_red_ranger_fresh.html"
    if Path(produced).resolve() != friendly.resolve():
        Path(produced).replace(friendly)
    size_mb = friendly.stat().st_size / 1e6
    log.info("  -> %s (%.1f MB)", friendly, size_mb)
    print(f"\n✓ offline evaluation report: file://{friendly}  ({size_mb:.1f} MB)")
    print("  (metric values are synthetic/illustrative; graphs + structure are real)")


if __name__ == "__main__":
    main()
