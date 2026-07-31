"""Executable cross-repo eval-seam contract test (register C-192, #264).

Pins the REAL views-pipeline-core → views-reporting seam that every other test
in this repo mocks (epic #262 S2). The demonstrated failure class is the #181
near-miss: our lockfile pinned a pipeline-core commit calling a deleted
``generate(wandb_run=)`` signature and green CI hid it, because nothing on our
side executed the seam. These tests parse and import pipeline-core's actual
stage code, so a drift on EITHER side fails loud here — before the coordinated
release (#179) can ship it.

Contract surfaces pinned (all verified against vpc 3.0.0 dev):

- ``ReportingStage.generate_evaluation_report`` calls
  ``evaluation_template.generate(source=…, target=…)`` (stage.py:236) —
  call shape via AST (survives reformatting; a kwarg rename fails).
- Our ``EvaluationReportTemplate.generate`` binds exactly that call.
- The stage's ``MetricFrameFileSource(root=…, run_type=…, target=…,
  primary_model=…)`` construction binds our ``__init__``, with
  ``root=context.model_path.data_generated``.
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

import pytest

reporting_stage = pytest.importorskip("views_pipeline_core.managers.reporting.stage")
evaluation_stage = pytest.importorskip("views_pipeline_core.managers.evaluation.stage")

from views_reporting.sources import MetricFrameFileSource  # noqa: E402
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


def test_stage_constructs_source_with_our_init_contract():
    """The stage's ``MetricFrameFileSource(…)`` construction binds our
    ``__init__``, and roots it at ``context.model_path.data_generated``."""
    calls = _ctor_calls("MetricFrameFileSource")
    assert calls, "stage no longer constructs MetricFrameFileSource"
    sig = inspect.signature(MetricFrameFileSource.__init__)
    for call in calls:
        assert not call.args
        kwargs = _keywords(call)
        sig.bind(None, **{k: object() for k in kwargs})
        (root_kw,) = [kw for kw in call.keywords if kw.arg == "root"]
        assert isinstance(root_kw.value, ast.Attribute)
        assert root_kw.value.attr == "data_generated", (
            "the locked path contract roots at <data_generated> "
            "(their C-202 / our C-192)"
        )


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
