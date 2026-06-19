"""Offline WandB-run doubles for evaluation-report tests and demos.

TEST/DEV ONLY — this module must never be imported from `views_reporting/`
(it would violate the ADR-002 layering and pull a test concern into the package).

`EvaluationReportTemplate` reads only a small, closed surface off the WandB run
object (`.summary`, `.config`, `.id`, `.url`, `.user.name/.username`) and, for
ensembles, resolves each constituent via the `evaluation_run_resolver` seam
(`list_runs()` per constituent, #116). These doubles reproduce exactly that surface
so the full eval report can be generated offline.

Honesty note: the metric VALUES carried in the fixtures are *illustrative*. The
report STRUCTURE and the rendered graphs they drive are real; the numbers are not
from a real evaluation.
"""

import json
from pathlib import Path
from typing import Optional


class _FakeUser:
    def __init__(self, name: str = "views-bot", username: str = "views-bot"):
        self.name = name
        self.username = username


class FakeWandbRun:
    """Minimal stand-in for `wandb.apis.public.runs.Run` exposing only the
    attributes `EvaluationReportTemplate` reads."""

    def __init__(
        self,
        summary: dict,
        config: dict,
        run_id: str = "offline-demo",
        url: str = "https://wandb.ai/views-platform/offline/runs/demo",
        user: Optional[_FakeUser] = None,
    ):
        self.summary = dict(summary)
        self.config = dict(config)
        self.id = run_id
        self.url = url
        self.user = user or _FakeUser()


def load_fake_run(path) -> FakeWandbRun:
    """Build a FakeWandbRun from a `{summary, config, id?, url?, user?}` JSON file."""
    d = json.loads(Path(path).read_text())
    user = _FakeUser(**d["user"]) if d.get("user") else None
    return FakeWandbRun(
        summary=d["summary"],
        config=d["config"],
        run_id=d.get("id", "offline-demo"),
        url=d.get("url", "https://wandb.ai/views-platform/offline/runs/demo"),
        user=user,
    )


def make_list_runs(runs_by_model: dict):
    """Return a drop-in replacement for
    `views_reporting.templates.reports.evaluation_run_resolver.list_runs(entity,
    model_name, run_type)` that resolves a constituent's runs from an in-memory
    mapping (no network), newest-first.

    A mapping value that is:
      * a list/tuple   -> returned as the newest-first run list (model multiple runs);
      * a single run   -> wrapped as a one-element list (convenience for the common case);
      * a BaseException -> *raised* (transient-failure modelling, mirrors #106);
      * absent / None  -> ``[]`` (ABSENT: the model has no resolvable run).

    The exception and absent branches preserve the #105/#177 failure-category
    semantics the prior `make_get_latest_run` double encoded.
    """

    def _fake_list_runs(entity: str, model_name: str, run_type: str):
        value = runs_by_model.get(model_name)
        if isinstance(value, BaseException):
            raise value
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]

    return _fake_list_runs
