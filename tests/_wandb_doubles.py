"""Offline WandB-run doubles for evaluation-report tests and demos.

TEST/DEV ONLY — this module must never be imported from `views_reporting/`
(it would violate the ADR-002 layering and pull a test concern into the package).

`EvaluationReportTemplate` reads only a small, closed surface off the WandB run
object (`.summary`, `.config`, `.id`, `.url`, `.user.name/.username`) and, for
ensembles, `get_latest_run()` per constituent. These doubles reproduce exactly
that surface so the full eval report can be generated offline.

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


def make_get_latest_run(runs_by_model: dict):
    """Return a drop-in replacement for
    `views_pipeline_core.modules.wandb.get_latest_run(entity, model_name, run_type)`
    that resolves constituent runs from an in-memory mapping (no network).

    Failure-category modelling (mirrors pipeline-core's resolver, see #106): a
    mapping value that is an exception instance is *raised* (the "Could not find
    project" branch), an absent key resolves to ``None`` (the "returned nothing"
    branch), and any other value is returned as the run. Backward-compatible:
    existing callers pass only `FakeWandbRun`/absent, which are unaffected.
    """

    def _fake_get_latest_run(entity: str, model_name: str, run_type: str):
        value = runs_by_model.get(model_name)
        if isinstance(value, BaseException):
            raise value
        return value

    return _fake_get_latest_run
