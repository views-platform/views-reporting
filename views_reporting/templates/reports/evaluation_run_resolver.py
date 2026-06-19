"""Metric-aware resolution of a constituent's evaluation run (interim, C-48 / #116).

INTERIM SCAFFOLDING — this whole module is deleted in Phase 3 (C-108), when
views-reporting stops *acquiring* evaluation data at render time and instead
*receives* a typed ``MetricFrame`` through an injected ``EvaluationSource`` adapter.
Until views-frames exists, this seam keeps the ensemble evaluation report usable.

Why it exists: pipeline-core's ``get_latest_run`` returns the newest *created* run
(finished, with metrics), which for heavily re-run models is often a non-eval run that
carries none of *this target's* canonical metrics — so the report rendered "not
calculated" for runs whose real scores sat in an earlier run (the production 22/25).
This module selects, instead, the newest run that actually carries the canonical
metrics for the target.

Self-contained by design (SDP): it enumerates runs via wandb's **public** ``Api`` and
views-reporting's own canonical-metric matching — it does not reach into pipeline-core
internals. The cross-constituent partition/level consistency check in the caller remains
the loud guard against rendering a wrong-partition number; this module does not add a
silent "guess" path. Known interim limitation: same-partition *stale re-logs* cannot be
distinguished without provenance (resolved by the Phase-3 ``MetricFrame``; see C-110).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

import wandb
from views_pipeline_core.modules.wandb import format_evaluation_dict

from views_reporting.reports import search_for_item_name

logger = logging.getLogger(__name__)

WANDB_ENTITY = "views_pipeline"


class Resolution(Enum):
    """Outcome category for resolving one constituent's evaluation run."""

    RESOLVED = "resolved"
    ABSENT = "absent"


@dataclass(frozen=True)
class RunResolution:
    """The result of resolving one constituent. ``run`` is set iff ``RESOLVED``."""

    status: Resolution
    run: Optional[object] = None
    detail: str = ""


def list_runs(entity: str, model_name: str, run_type: str) -> list:
    """All finished, metrics-bearing runs for ``{entity}/{model_name}_{run_type}``,
    newest-first. Self-contained (public ``wandb.Api``), mirroring pipeline-core's
    qualifying contract without importing its internals.

    A missing project ("could not find project" — normal for offline models) yields an
    empty list (ABSENT). Any other error propagates so the caller can treat it as a
    transient failure and retry. Tests monkeypatch this module-level symbol.
    """
    project = f"{entity}/{model_name}_{run_type}"
    api = wandb.Api()
    try:
        runs = list(api.runs(project, include_sweeps=False))
    except Exception as exc:  # noqa: BLE001 — classify absent vs transient by message
        if "could not find project" in str(exc).lower():
            return []
        raise
    runs.sort(key=lambda run: run.created_at, reverse=True)
    return [
        run
        for run in runs
        if getattr(run, "state", "finished") == "finished"
        and len(dict(run.summary)) > 1
    ]


def _carries_canonical_metrics(
    run, target: str, eval_type: str, canonical_metrics: Iterable[str]
) -> bool:
    """True iff ``run``'s summary carries *any* canonical metric token for ``target``
    under ``eval_type`` — the discriminator that separates an evaluation run (full
    metric set) from a non-eval run (none)."""
    keys = list(format_evaluation_dict(dict(run.summary)).keys())
    return any(
        search_for_item_name(keys, [eval_type, metric, target, "mean"])
        for metric in canonical_metrics
    )


def resolve_constituent_run(
    *,
    model: str,
    run_type: str,
    target: str,
    eval_type: str,
    canonical_metrics: Iterable[str],
    runs_lister=None,
) -> RunResolution:
    """Resolve one constituent's evaluation run, metric-aware.

    Enumerates the model's runs newest-first and returns the newest that carries the
    canonical metrics for ``target`` (``RESOLVED``); ``ABSENT`` if none do. When no
    metric standard is active (``canonical_metrics`` empty), falls back to the newest
    run, preserving prior behavior. A transient enumeration error is *not* caught here
    — it propagates so the caller can retry-once-then-degrade.
    """
    lister = runs_lister or list_runs  # late-bound module global → monkeypatchable
    runs = lister(WANDB_ENTITY, model, run_type)
    if not runs:
        return RunResolution(Resolution.ABSENT, detail="no run found")

    canonical_metrics = list(canonical_metrics)
    if not canonical_metrics:
        # No active metric standard: cannot be metric-aware — keep prior behavior.
        return RunResolution(
            Resolution.RESOLVED,
            run=runs[0],
            detail="newest run (no metric standard active)",
        )

    metric_bearing = [
        run
        for run in runs
        if _carries_canonical_metrics(run, target, eval_type, canonical_metrics)
    ]
    if not metric_bearing:
        return RunResolution(
            Resolution.ABSENT,
            detail="no run carries the canonical metrics for this target",
        )

    selected = metric_bearing[0]
    if selected is not runs[0]:
        # Observability: we passed over the newest-created run because it lacked the
        # canonical metrics for this target (the C-48 / 22-of-25 case).
        logger.info(
            "Constituent '%s': selected an earlier metric-bearing run over the "
            "newest-created run (the newest run lacks the canonical metrics for '%s').",
            model,
            target,
        )
    return RunResolution(
        Resolution.RESOLVED, run=selected, detail="newest metric-bearing run"
    )
