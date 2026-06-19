"""Tests from the /falsify audit of #105 + #106 (2026-06-18).

P4 (coverage) — IMPLEMENTED BELOW: #105 added an opt-in `strict_constituents`
mode (raise on any absent/degraded constituent) that had no test. The strict
path is now verified by `test_strict_constituents_raises_on_absent_constituent`.

P3 (deployment/dependency) — NOT a test; tracked as risk **C-48** in
`reports/technical_risk_register.md`. The audit's narrower P3 framing (absent-vs-
degraded depends on the installed pipeline-core honoring the #177 get_latest_run
contract) is one symptom of the deeper root cause C-48 records: the report reads
constituent metrics from the WandB *cloud* replica instead of the authoritative
local `eval_*.parquet`. The original P3 "guard" made a live WandB call (can't run
in CI; the real env/version skew it checked is exactly what CI cannot see — C-46),
so it is intentionally NOT a committed test. Remediation is an open team design
question (see C-48); do not ship to PyPI against a pipeline-core release lacking
#177 without bumping the pin floor.
"""
import pytest


@pytest.mark.red_team
def test_strict_constituents_raises_on_absent_constituent(tmp_path, monkeypatch):
    """P4 (now implemented): with ``strict_constituents=True`` and a declared
    constituent that resolves to ABSENT (no metric-bearing run), report-content
    generation MUST raise ``ValueError`` naming the absent model — not
    degrade-and-announce. Drives ``_add_report_content`` directly through the
    offline `make_list_runs` seam (no network), mirroring
    ``test_falsification_missing_constituent.py``."""
    import sys
    from pathlib import Path as _Path
    from unittest.mock import MagicMock

    try:
        from views_reporting.reports import ReportModule
        from views_reporting.templates.reports.evaluation import EvaluationReportTemplate
    except ImportError:
        pytest.skip("views_pipeline_core not installed")

    sys.path.insert(0, str(_Path(__file__).parent))
    from _wandb_doubles import FakeWandbRun, make_list_runs

    import views_reporting.templates.reports.evaluation_run_resolver as resolvermod

    target = "lr_ged_sb"
    present, absent = "alpha_ranger", "charlie_ranger"

    def _run(name: str) -> FakeWandbRun:
        return FakeWandbRun(
            summary={
                "_timestamp": 1717560000,
                "runtime": 1800,
                f"time-series-wise_MSLE_mean_{target}_best": 0.51,
            },
            config={
                "name": name, "level": "cm", "steps": [1, 36],
                "eval_type": "standard",
                "calibration": {"train": [121, 444], "test": [445, 492]},
            },
        )

    # Resolver returns the present model only; `absent` is omitted → [] (ABSENT).
    monkeypatch.setattr(
        resolvermod, "list_runs", make_list_runs({present: _run(present)})
    )

    model_path = MagicMock()
    model_path.target = "ensemble"
    model_path._get_generated_pf_prediction_paths.return_value = []
    config = {
        "name": "first_love", "level": "cm", "prediction_format": "prediction_frame",
        "targets": [target], "regression_point_metrics": ["MSLE"],
        "models": [present, absent], "strict_constituents": True,
    }
    template = EvaluationReportTemplate(config, model_path, run_type="calibration")
    report_manager = ReportModule()

    with pytest.raises(ValueError, match=absent):
        template._add_report_content(
            report_manager,
            {"name": "first_love", "level": "cm"},
            {f"time-series-wise_MSLE_mean_{target}_best": 0.42},
            target,
        )
