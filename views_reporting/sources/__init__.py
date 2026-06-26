"""Evaluation metric sources (Ingestion) — the injected ``EvaluationSource`` the eval
report renders from (ADR-018 / C-108).

Unlike ``loaders/`` there is deliberately no registry: a source is *injected* by the
caller, not dispatched by a format token in the data.
"""

from views_reporting.sources._protocol import EvaluationSource
from views_reporting.sources.evaluation_provenance import EvaluationProvenance
from views_reporting.sources.metric_frame_file_source import MetricFrameFileSource
from views_reporting.sources.metric_value import (
    AmbiguousMetric,
    mean_metric_value,
    unique_axis_value,
)
from views_reporting.sources.wandb_evaluation_source import WandbEvaluationSource

__all__ = [
    "EvaluationSource",
    "EvaluationProvenance",
    "MetricFrameFileSource",
    "WandbEvaluationSource",
    "AmbiguousMetric",
    "mean_metric_value",
    "unique_axis_value",
]
