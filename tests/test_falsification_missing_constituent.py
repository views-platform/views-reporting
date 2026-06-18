"""Falsification: a declared ensemble constituent that fails to resolve is
silently dropped from the Model-Metrics table (#105).

`EvaluationReportTemplate._add_report_content` resolves each declared constituent
via the module-level `get_latest_run`. A constituent that resolves to nothing
(`if latest_run:` filters it) or whose resolution raises (`except Exception …
Skipping … continue`) is dropped with only a `logger.warning` — it produces no
row and its name appears nowhere in the report. Because the metric tables render
with `to_html(index=False)` (report.py), the constituent name can only reach the
HTML via a text note, so today a dropped constituent is invisible either way.

These two failure modes are distinct under the now-final `get_latest_run`
contract (views-pipeline-core #177, commit 3a71970):
  * ABSENT — `get_latest_run` returns ``None`` (offline model / no cloud run).
    The constituent is genuinely missing and must be SURFACED as missing.
  * TRANSIENT — `get_latest_run` RAISES (network/API hiccup). The constituent is
    not known to be missing; it must be handled DISTINCTLY (retry / mark
    degraded), NOT announced as a permanent missing constituent — but it must
    still not vanish silently.

Today both collapse to the same silent drop. These characterization tests lock
that bug on the existing offline seam (`make_get_latest_run`, no network), which
already models both `None` and raise. They are `xfail(strict=True)` — they xfail
today and will xpass once #105 (degrade-and-announce + opt-in strict) makes each
case visible; `strict=True` then turns the xpass into a failure, forcing removal
of the markers so the tests become live regression guards. Idiom mirrors
`tests/test_falsification_operational.py`.

The assertions lock the durable invariant — *the constituent does not vanish
silently* — without over-fitting #105's exact missing-vs-degraded wording (that
distinction is asserted precisely by #105's own tests). If #105 instead routes a
case through its opt-in strict-raise mode, that test becomes a one-line change to
`pytest.raises(...)`.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

try:
    from views_pipeline_core.data.handlers import CMDataset  # noqa: F401

    from views_reporting.reports import ReportModule
    from views_reporting.templates.reports.evaluation import EvaluationReportTemplate
except ImportError:
    pytest.skip("views_pipeline_core not installed", allow_module_level=True)

sys.path.insert(0, str(Path(__file__).parent))
from _wandb_doubles import FakeWandbRun, make_get_latest_run  # noqa: E402

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
    import views_reporting.templates.reports.evaluation as evalmod

    monkeypatch.setattr(evalmod, "get_latest_run", make_get_latest_run(runs_by_model))
    report_manager = ReportModule()
    template._add_report_content(
        report_manager,
        {"name": "first_love", "level": "cm"},
        {f"time-series-wise_MSLE_mean_{TARGET}_best": 0.42},
        TARGET,
    )
    out = tmp_path / "report.html"
    report_manager.export_as_html(str(out))
    return out.read_text()


@pytest.mark.red_team
@pytest.mark.xfail(reason="#105: absent constituent dropped silently", strict=True)
def test_absent_constituent_is_surfaced_as_missing(tmp_path, monkeypatch):
    """A declared constituent the resolver returns ``None`` for is the ABSENT
    category under the #177 contract (no cloud run) and must be SURFACED as
    missing. Today it is silently dropped → this assertion fails (the bug); it
    flips to passing once #105 (degrade-and-announce) lands."""
    template = _ensemble_template(CONSTITUENTS)
    runs = {name: _constituent_run(name) for name in RESOLVED}  # MISSING omitted
    html = _render(template, runs, tmp_path, monkeypatch)
    assert MISSING in html, (
        f"declared constituent '{MISSING}' did not resolve and is named nowhere "
        "in the report — the silent drop of #105"
    )


@pytest.mark.red_team
@pytest.mark.xfail(reason="#105: transient resolution failure dropped silently", strict=True)
def test_transient_failure_is_not_silently_dropped(tmp_path, monkeypatch):
    """A declared constituent whose resolution RAISES is a *transient* failure
    under the #177 contract (raise ⇒ retry / mark degraded), NOT a genuine
    absence. The broad `except Exception … continue` must not silently swallow
    it: it must remain visible in the report (degraded), handled distinctly from
    an absent (`None`) constituent. Today it vanishes with only a logger.warning,
    so its name appears nowhere — this assertion fails until #105 surfaces it."""
    template = _ensemble_template(CONSTITUENTS)
    runs = {name: _constituent_run(name) for name in RESOLVED}
    # Transient category per #177: get_latest_run propagates the exception.
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
