"""Regression tests for #116 — metric-aware constituent run selection (interim C-48).

These began as xfail stubs from the Sprint-1 readiness falsification audit (2026-06-19),
encoding the corrected executable spec. They are now **live** against the implemented
`evaluation_run_resolver` seam. All drive the synthetic `_wandb_doubles` (no network, no
on-disk parquet) so they run in CI — the P8 finding (an on-disk `*.parquet` fixture would
be gitignored and skip in CI, the C-46 trap).

Coverage:
  * metric-aware selection picks the newest run that CARRIES the canonical metrics,
    skipping a newer non-eval run (the production 22/25 case);
  * the partition/level consistency check operates on the metric-aware-SELECTED run, not
    on the newest-created run;
  * a genuinely inconsistent selected run across constituents raises LOUDLY (no silent
    wrong number — the C-110 protection);
  * one constituent row is sourced from exactly one run (no cross-run mixing).
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

try:
    from views_pipeline_core.data.handlers import CMDataset  # noqa: F401

    from views_reporting.reports import ReportModule
    from views_reporting.templates.reports.evaluation import EvaluationReportTemplate
    from views_reporting.templates.reports.evaluation_run_resolver import (
        Resolution,
        resolve_constituent_run,
    )
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).parent))
from _wandb_doubles import FakeWandbRun, make_list_runs  # noqa: E402

TARGET = "lr_ged_sb"
# Canonical reg-point metrics are (MSLE, MSE, MCR_point, y_hat_bar); a run carrying the
# MSLE token is metric-bearing for the (regression, point) cell.
_METRIC_KEY = f"time-series-wise_MSLE_mean_{TARGET}_best"
_CANONICAL = ["MSLE", "MSE", "MCR_point", "y_hat_bar"]


def _metric_bearing_run(name="c1", level="cm", value=0.51) -> FakeWandbRun:
    return FakeWandbRun(
        summary={"_timestamp": 1717560000, "runtime": 1800, _METRIC_KEY: value},
        config={
            "name": name,
            "level": level,
            "steps": [1, 36],
            "eval_type": "standard",
            "calibration": {"train": [121, 444], "test": [445, 492]},
        },
    )


def _metric_less_run(name="c1", level="cm") -> FakeWandbRun:
    """A non-eval run: finished, >1 summary key, but no canonical metric tokens
    (mirrors the production `_timestamp=null` runs that shadowed the real eval run)."""
    return FakeWandbRun(
        summary={"some_system_stat": 1, "another_stat": 2},
        config={"name": name, "level": level},
    )


# ── resolver-level units ────────────────────────────────────────────────────────────


def test_metric_aware_selection_picks_earlier_metric_bearing_run():
    """The newest-created run is metric-less; selection passes over it to the earlier
    run that actually carries the canonical metrics (the C-48 mechanism)."""
    newest = _metric_less_run()
    earlier = _metric_bearing_run()
    res = resolve_constituent_run(
        model="c1",
        run_type="calibration",
        target=TARGET,
        eval_type="time-series-wise",
        canonical_metrics=_CANONICAL,
        runs_lister=make_list_runs({"c1": [newest, earlier]}),  # newest-first
    )
    assert res.status is Resolution.RESOLVED
    assert res.run is earlier  # not the newest-created run


def test_no_metric_bearing_run_is_absent_not_a_wrong_guess():
    """When no run carries the canonical metrics, the constituent is ABSENT (announced),
    never silently resolved to a metric-less run."""
    res = resolve_constituent_run(
        model="c1",
        run_type="calibration",
        target=TARGET,
        eval_type="time-series-wise",
        canonical_metrics=_CANONICAL,
        runs_lister=make_list_runs({"c1": [_metric_less_run(), _metric_less_run()]}),
    )
    assert res.status is Resolution.ABSENT


def test_one_constituent_row_is_sourced_from_exactly_one_run():
    """With several metric-bearing runs, resolution returns exactly one (the newest) —
    a row is never assembled from multiple runs (C-110: one row = one evaluation)."""
    newest = _metric_bearing_run(value=0.50)
    older = _metric_bearing_run(value=0.99)
    res = resolve_constituent_run(
        model="c1",
        run_type="calibration",
        target=TARGET,
        eval_type="time-series-wise",
        canonical_metrics=_CANONICAL,
        runs_lister=make_list_runs({"c1": [newest, older]}),
    )
    assert res.status is Resolution.RESOLVED
    assert res.run is newest  # single, deterministic run — no mixing


# ── template-level integration ──────────────────────────────────────────────────────


def _ensemble_template(models):
    model_path = MagicMock()
    model_path.target = "ensemble"
    model_path.model_name = "first_love"
    model_path._get_generated_pf_prediction_paths.return_value = []
    config = {
        "name": "first_love",
        "level": "cm",
        "prediction_format": "prediction_frame",
        "targets": [TARGET],
        "regression_point_metrics": ["MSLE"],  # → regression/point cell active
        "models": models,
    }
    return EvaluationReportTemplate(config, model_path, run_type="calibration")


def _render(template, runs_by_model, tmp_path, monkeypatch):
    import views_reporting.templates.reports.evaluation_run_resolver as resolvermod

    monkeypatch.setattr(resolvermod, "list_runs", make_list_runs(runs_by_model))
    report_manager = ReportModule()
    template._add_report_content(
        report_manager,
        {"name": "first_love", "level": "cm"},
        {_METRIC_KEY: 0.42},
        TARGET,
    )
    out = tmp_path / "report.html"
    report_manager.export_as_html(str(out))
    return out.read_text()


@pytest.mark.red_team
def test_production_22_of_25_regression(tmp_path, monkeypatch):
    """The headline regression: a constituent whose NEWEST run is metric-less but whose
    EARLIER run carries the score renders that score — not 'not calculated'. Pre-#116
    (newest-created selection) this blanked 22/25 constituents in production."""
    runs = {"c1": [_metric_less_run("c1"), _metric_bearing_run("c1", value=0.51)]}
    html = _render(_ensemble_template(["c1"]), runs, tmp_path, monkeypatch)
    assert "0.51" in html, "the earlier metric-bearing run's score did not render"


@pytest.mark.red_team
def test_partition_check_operates_on_the_selected_run(tmp_path, monkeypatch):
    """The newest-created run is metric-less AND has a divergent level (pgm); the earlier
    metric-bearing run is partition-consistent (cm). Metric-aware selection picks the cm
    run, so the cross-constituent level check sees a consistent level and does NOT raise —
    proving the check runs on the SELECTED run, not the newest-created one."""
    runs = {
        "c1": [
            _metric_less_run("c1", level="pgm"),  # newest, divergent, no metrics
            _metric_bearing_run("c1", level="cm", value=0.51),  # selected
        ]
    }
    html = _render(_ensemble_template(["c1"]), runs, tmp_path, monkeypatch)
    assert "0.51" in html  # rendered cleanly; no LoA mismatch raised


@pytest.mark.red_team
def test_inconsistent_selected_runs_across_constituents_raise_loudly(tmp_path, monkeypatch):
    """Two constituents whose SELECTED metric-bearing runs disagree on level → the
    existing cross-constituent check raises a loud ValueError. C-110 protection: a
    partition/level mismatch surfaces loudly, never as a silent wrong number."""
    import views_reporting.templates.reports.evaluation_run_resolver as resolvermod

    runs = {
        "c1": [_metric_bearing_run("c1", level="cm", value=0.5)],
        "c2": [_metric_bearing_run("c2", level="pgm", value=0.6)],
    }
    monkeypatch.setattr(resolvermod, "list_runs", make_list_runs(runs))
    template = _ensemble_template(["c1", "c2"])
    report_manager = ReportModule()
    with pytest.raises(ValueError, match="(?i)mismatch"):
        template._add_report_content(
            report_manager,
            {"name": "first_love", "level": "cm"},
            {_METRIC_KEY: 0.42},
            TARGET,
        )
