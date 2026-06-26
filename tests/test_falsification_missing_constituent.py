"""Falsification: a declared ensemble constituent that fails to resolve is
silently dropped from the Model-Metrics table (#105).

`EvaluationReportTemplate._add_report_content` resolves each declared constituent
via the `evaluation_run_resolver` seam (`list_runs`; pre-#116 it was the
module-level `get_latest_run`). A constituent that resolves to nothing (ABSENT) or
whose resolution raises was, in the original bug, dropped with only a
`logger.warning` — producing no row and naming the constituent nowhere in the
report. Because the metric tables render with `to_html(index=False)` (report.py),
the constituent name can only reach the HTML via a text note, so a dropped
constituent is invisible either way.

These two failure modes are distinct (the resolver honors the #177 `get_latest_run`
contract, views-pipeline-core commit 3a71970):
  * ABSENT — the resolver finds no metric-bearing run (offline model / no cloud
    run). The constituent is genuinely missing and must be SURFACED as missing.
  * TRANSIENT — run enumeration RAISES (network/API hiccup). The constituent is
    not known to be missing; it must be handled DISTINCTLY (retry / mark
    degraded), NOT announced as a permanent missing constituent — but it must
    still not vanish silently.

Originally both collapsed to the same silent drop. #105 (degrade-and-announce +
opt-in strict) fixed that: absent constituents are announced as missing and
transient ones are retried then surfaced as degraded. These tests, which began as
`xfail(strict=True)` characterizations, are now **live regression guards** on the
existing offline seam (`make_list_runs`, no network — it models both the absent
`[]` and the transient raise). They assert the durable invariant — *a declared
constituent does not vanish silently* — without over-fitting #105's exact
missing-vs-degraded wording.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

try:
    from views_pipeline_core.data.handlers import CMDataset  # noqa: F401

    from views_reporting.reports import ReportModule
    from views_reporting.sources import WandbEvaluationSource
    from views_reporting.templates.reports.evaluation import EvaluationReportTemplate
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).parent))
from _wandb_doubles import FakeWandbRun, make_list_runs  # noqa: E402

TARGET = "lr_ged_sb"
# Distinctive constituent names — unlikely to appear incidentally in the HTML.
CONSTITUENTS = ["alpha_ranger", "bravo_ranger", "charlie_ranger"]
MISSING = "charlie_ranger"
RESOLVED = ["alpha_ranger", "bravo_ranger"]


def _constituent_run(name: str) -> FakeWandbRun:
    """A partition-consistent constituent run (level cm, calibration window) so the
    partition-verification loop in `_add_report_content` does not raise for the
    wrong reason. Shape mirrors `test_e2e_eval_report.py::_constituent_run`."""
    return FakeWandbRun(
        summary={
            "_timestamp": 1717560000,
            "runtime": 1800,
            f"time-series-wise_MSLE_mean_{TARGET}_best": 0.51,
        },
        config={
            "name": name,
            "level": "cm",
            "steps": [1, 36],
            "eval_type": "standard",
            "calibration": {"train": [121, 444], "test": [445, 492]},
        },
    )


def _ensemble_template(models):
    """Build an ensemble EvaluationReportTemplate driven directly via
    `_add_report_content` (fast, no `generate()`): one active cell
    (regression/point) and the sample-graphs path short-circuited to a note."""
    model_path = MagicMock()
    model_path.target = "ensemble"
    model_path.model_name = "first_love"
    # Empty PF discovery → sample-graphs degrade to a visible note without
    # touching ModelPathManager (matches test_e2e_eval_report.py).
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
    # Constituent resolution still flows through the interim WandbEvaluationSource,
    # which wraps the same `evaluation_run_resolver.list_runs` seam (#173 / C-108).
    import views_reporting.templates.reports.evaluation_run_resolver as resolvermod

    monkeypatch.setattr(resolvermod, "list_runs", make_list_runs(runs_by_model))
    subject_run = FakeWandbRun(
        summary={f"time-series-wise_MSLE_mean_{TARGET}_best": 0.42},
        config={"name": "first_love", "level": "cm"},
    )
    source = WandbEvaluationSource(
        subject_run,
        run_type="calibration",
        config=template.config,
        target=TARGET,
        primary_model="first_love",
        eval_types=template.eval_types,
    )
    report_manager = ReportModule()
    template._add_report_content(report_manager, source, TARGET)
    out = tmp_path / "report.html"
    report_manager.export_as_html(str(out))
    return out.read_text()


@pytest.mark.red_team
def test_absent_constituent_is_surfaced_as_missing(tmp_path, monkeypatch):
    """A declared constituent the resolver returns ``None`` for is the ABSENT
    category under the #177 contract (no cloud run) and must be SURFACED as
    missing. #105 (degrade-and-announce) makes this pass: the absent model is
    named in a visible note rather than silently dropped."""
    template = _ensemble_template(CONSTITUENTS)
    runs = {name: _constituent_run(name) for name in RESOLVED}  # MISSING omitted
    html = _render(template, runs, tmp_path, monkeypatch)
    assert MISSING in html, (
        f"declared constituent '{MISSING}' did not resolve and is named nowhere "
        "in the report — the silent drop of #105"
    )


@pytest.mark.red_team
def test_transient_failure_is_not_silently_dropped(tmp_path, monkeypatch):
    """A declared constituent whose resolution RAISES is a *transient* failure
    under the #177 contract (raise ⇒ retry / mark degraded), NOT a genuine
    absence. The broad `except Exception … continue` must not silently swallow
    it. #105 retries once then surfaces it as degraded (distinct from absent), so
    its name appears in the report rather than vanishing."""
    template = _ensemble_template(CONSTITUENTS)
    runs = {name: _constituent_run(name) for name in RESOLVED}
    # Transient category per #177: run resolution propagates the exception.
    runs[MISSING] = RuntimeError("transient WandB/API error for charlie_ranger")
    html = _render(template, runs, tmp_path, monkeypatch)
    assert MISSING in html, (
        f"transient constituent '{MISSING}' was silently swallowed by the broad "
        "`except Exception … continue` and is named nowhere in the report; the "
        "#177 contract requires it be surfaced (degraded), distinct from absent"
    )


@pytest.mark.green_team
def test_all_constituents_resolve_renders_cleanly(tmp_path, monkeypatch):
    """Wiring / behavior-preservation guard: when every declared constituent
    resolves, the fully-resolved path still builds the active-cell table without
    error. (Deliberately asserts no #105-specific 'missing' note — that text is
    undecided until #105 lands.)"""
    template = _ensemble_template(CONSTITUENTS)
    runs = {name: _constituent_run(name) for name in CONSTITUENTS}
    html = _render(template, runs, tmp_path, monkeypatch)
    assert "Regression (point)" in html  # active canonical cell rendered
