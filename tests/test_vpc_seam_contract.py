"""Executable cross-repo eval-seam contract test (register C-192, #264).

Pins the REAL views-pipeline-core → views-reporting seam that every other test
in this repo mocks (epic #262 S2). The demonstrated failure class is the #181
near-miss: our lockfile pinned a pipeline-core commit calling a deleted
``generate(wandb_run=)`` signature and green CI hid it, because nothing on our
side executed the seam. These tests parse and import pipeline-core's actual
stage code, so a drift on EITHER side fails loud here — before the coordinated
release (#179) can ship it.

Contract surfaces pinned (verified against the RELEASED vpc 3.3.0):

- ``ReportingStage.generate_evaluation_report`` calls
  ``evaluation_template.generate(source=…, target=…)`` —
  call shape via AST (survives reformatting; a kwarg rename fails).
- Our ``EvaluationReportTemplate.generate`` binds exactly that call.
- The stage constructs pipeline-core's ``PerModelMetricFrameSource`` (one of
  OUR ``MetricFrameFileSource``s per model, each at that model's own
  ``data_generated`` — vpc #485 / our C-215) with ``primary_root=
  context.model_path.data_generated`` and NO ``root_of`` override — the
  default per-model resolver must be in force. Until vpc 3.3.0 this file
  faithfully locked the old single subject-rooted source, i.e. the defect.
- A real per-model round-trip: frames saved under TWO different roots resolve
  through the stage's source via our public ``metric_frame()`` — never a
  shared root (the fixture blind spot that hid C-215).
- The on-disk layout — "LOCKED cross-repo path contract" (their C-202, our
  C-192): our ``_frame_dir`` must equal
  ``root / model / run_type / METRICFRAME_DIR_PREFIX + target`` using the
  producer's OWN exported constant
  (``views_pipeline_core.managers.evaluation.stage.METRICFRAME_DIR_PREFIX``).
- Bonus: both ``forecast_template.generate(…)`` call sites bind our
  ``ForecastReportTemplate.generate`` signature.

Skip-if-absent: a CI checkout without views-pipeline-core skips loud (the
C-46 fixture-skip contract), never silently passes.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

reporting_stage = pytest.importorskip("views_pipeline_core.managers.reporting.stage")
evaluation_stage = pytest.importorskip("views_pipeline_core.managers.evaluation.stage")
metric_frame_source = pytest.importorskip(
    "views_pipeline_core.managers.reporting.metric_frame_source"
)

from views_reporting.sources import MetricFrameFileSource  # noqa: E402
from views_reporting.sources.metric_value import mean_metric_value  # noqa: E402
from views_reporting.templates.reports.evaluation import (  # noqa: E402
    EvaluationReportTemplate,
)
from views_reporting.templates.reports.forecast import (  # noqa: E402
    ForecastReportTemplate,
)


def _stage_calls(receiver: str, method: str) -> list[ast.Call]:
    """All ``<receiver>.<method>(…)`` Call nodes in the REAL stage source."""
    tree = ast.parse(inspect.getsource(reporting_stage))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == receiver
    ]


def _ctor_calls(class_name: str) -> list[ast.Call]:
    """All ``ClassName(…)`` Call nodes in the REAL stage source."""
    tree = ast.parse(inspect.getsource(reporting_stage))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == class_name
    ]


def _keywords(call: ast.Call) -> set[str]:
    kws = {kw.arg for kw in call.keywords}
    assert None not in kws, "**kwargs splat defeats the contract check"
    return kws


def test_stage_calls_eval_generate_with_source_and_target():
    """Their side of C-192: the stage's eval-report call is
    ``generate(source=…, target=…)`` — keyword-only, exactly these two."""
    calls = _stage_calls("evaluation_template", "generate")
    assert len(calls) == 1, "expected exactly one evaluation_template.generate call"
    (call,) = calls
    assert not call.args, "positional args would bypass the keyword contract"
    assert _keywords(call) == {"source", "target"}


def test_our_eval_generate_binds_their_call():
    """Our side: ``EvaluationReportTemplate.generate`` must bind the exact
    call the stage makes (a param rename/removal here breaks them)."""
    sig = inspect.signature(EvaluationReportTemplate.generate)
    sig.bind(None, source=object(), target="sb")  # raises TypeError on drift


def test_stage_constructs_the_per_model_source_rooted_at_the_subject():
    """The stage builds pipeline-core's per-model ``EvaluationSource``; the SUBJECT
    is rooted at ``context.model_path.data_generated``, every other model at its own
    (vpc #485 / our C-215).

    History: until vpc 3.3.0 the stage built ONE ``MetricFrameFileSource`` rooted at
    the subject, and this test faithfully locked that call — which meant it locked
    the defect that blanked every baseline/constituent row (C-215). Corrected in
    the same window as their fix, per the register's sequencing note.
    """
    calls = _ctor_calls("PerModelMetricFrameSource")
    assert calls, "stage no longer constructs PerModelMetricFrameSource"
    sig = inspect.signature(metric_frame_source.PerModelMetricFrameSource.__init__)
    for call in calls:
        assert not call.args
        kwargs = _keywords(call)
        sig.bind(None, **{k: object() for k in kwargs})
        # Exactly these, and in particular NO `root_of=`: an override could
        # re-express the C-215 defect (every model at the subject's root)
        # through the new class; production must use the default per-model
        # resolver.
        assert kwargs == {"primary_model", "primary_root", "run_type", "target"}, (
            f"stage constructs the per-model source with {sorted(kwargs)}"
        )
        (root_kw,) = [kw for kw in call.keywords if kw.arg == "primary_root"]
        assert isinstance(root_kw.value, ast.Attribute)
        assert root_kw.value.attr == "data_generated"


def test_per_model_source_resolves_frames_from_each_models_own_root(tmp_path):
    """A REAL per-model on-disk round-trip through the public port (#287):
    two models, two roots, frames written where the producer writes them
    (our locked layout under EACH model's own ``data_generated``), resolved
    through the stage's source class via ``metric_frame()`` (test resolver
    injected via ``root_of``; production's default resolver is vpc's to test).
    Never a shared root —
    the fixture blind spot that let C-215 pass CI for months. A source that
    regressed to subject-rooting resolves ``m1`` as None here."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from _eval_source_doubles import make_metric_frame

    prefix = evaluation_stage.METRICFRAME_DIR_PREFIX
    roots = {
        "ens": tmp_path / "ensembles" / "ens" / "data" / "generated",
        "m1": tmp_path / "models" / "m1" / "data" / "generated",
    }
    expected = {"ens": 0.42, "m1": 0.93}
    for model, value in expected.items():
        frame_dir = roots[model] / model / "calibration" / f"{prefix}sb"
        frame_dir.parent.mkdir(parents=True)
        make_metric_frame({"MSLE": value}, target="sb").save(frame_dir)

    source = metric_frame_source.PerModelMetricFrameSource(
        primary_model="ens",
        primary_root=roots["ens"],
        run_type="calibration",
        target="sb",
        root_of=lambda name: roots[name],
    )
    for model, value in expected.items():
        frame = source.metric_frame(model)
        assert frame is not None, f"{model} did not resolve from its own root"
        got = mean_metric_value(
            frame, eval_type="time-series-wise", target="sb", metric="MSLE"
        )
        assert got == pytest.approx(value)

    # Both rooted at the subject (the C-215 shape): the other model vanishes.
    regressed = metric_frame_source.PerModelMetricFrameSource(
        primary_model="ens",
        primary_root=roots["ens"],
        run_type="calibration",
        target="sb",
        root_of=lambda name: roots["ens"],
    )
    assert regressed.metric_frame("m1") is None


def test_frame_path_contract_uses_producers_own_prefix(tmp_path):
    """The LOCKED layout, pinned by executable equality against the
    producer's exported constant: ``root/<model>/<run_type>/metricframe_<target>``."""
    prefix = evaluation_stage.METRICFRAME_DIR_PREFIX
    source = MetricFrameFileSource(
        root=tmp_path, run_type="calibration", target="sb", primary_model="m"
    )
    assert (
        source._frame_dir("other_model")
        == tmp_path / "other_model" / "calibration" / f"{prefix}sb"
    )


def test_stage_forecast_generate_calls_bind_our_signature():
    """Bonus seam (same failure class): every ``forecast_template.generate(…)``
    call site in the stage binds our ``ForecastReportTemplate.generate``."""
    calls = _stage_calls("forecast_template", "generate")
    assert calls, "stage no longer calls forecast_template.generate"
    sig = inspect.signature(ForecastReportTemplate.generate)
    for call in calls:
        assert not call.args
        sig.bind(None, **{k: object() for k in _keywords(call)})
