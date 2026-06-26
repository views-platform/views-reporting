"""Test doubles for the EvaluationSource inversion (#173 / C-108).

Build synthetic ``MetricFrame``s and a trivial in-memory ``EvaluationSource`` so the
inverted evaluation report can be driven offline — no WandB, no pipeline-core producer.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple

import numpy as np
from views_evaluation.evaluation.metric_frame import AXES, MEAN_GROUP_ID, MetricFrame

from views_reporting.sources.evaluation_provenance import EvaluationProvenance


def make_metric_frame(
    values_by_metric: Dict[str, float],
    *,
    target: str,
    eval_type: str = "time-series-wise",
    partition: str = "p0",
    level: str = "cm",
    extra_rows: Iterable[Tuple[str, float]] = (),
) -> MetricFrame:
    """A MetricFrame of ``group_id="mean"`` rows for one (eval_type, target).

    ``values_by_metric`` maps metric → mean value. ``extra_rows`` adds further
    ``(metric, value)`` mean rows (use to inject a collision: the same metric twice →
    the C-116 ambiguity path).
    """
    rows = [(m, v) for m, v in values_by_metric.items()] + list(extra_rows)
    columns: Dict[str, list] = {axis: [] for axis in AXES}
    values: list = []
    for metric, value in rows:
        columns["eval_type"].append(eval_type)
        columns["target"].append(target)
        columns["metric"].append(metric)
        columns["group_id"].append(MEAN_GROUP_ID)
        columns["partition"].append(partition)
        columns["level"].append(level)
        values.append(value)
    return MetricFrame(
        values=np.asarray(values, dtype=np.float32).reshape(-1, 1),
        identifiers={axis: np.asarray(columns[axis], dtype=str) for axis in AXES},
    )


class FakeEvaluationSource:
    """In-memory ``EvaluationSource``: a ``{model: MetricFrame | None | Exception}`` map.

    ``None`` → absent; an ``Exception`` instance → raised (transient). ``provenance()``
    returns a fixed ``EvaluationProvenance``.
    """

    def __init__(
        self,
        frames_by_model: Dict[str, object],
        provenance: Optional[EvaluationProvenance] = None,
    ):
        self._frames = frames_by_model
        self._provenance = provenance or EvaluationProvenance(run_id="fake-run")

    def metric_frame(self, model: str) -> Optional[MetricFrame]:
        value = self._frames.get(model)
        if isinstance(value, BaseException):
            raise value
        return value

    def provenance(self) -> EvaluationProvenance:
        return self._provenance
