"""Pure read queries over a single MetricFrame (no I/O).

Separates "read a value out of the typed evaluation contract" from both *locating*
the frame (the EvaluationSource adapters) and *rendering* it (the report template),
so the metric-value semantics — including the C-116 ambiguity guard — live in one
testable place.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

import numpy as np
from views_evaluation.evaluation.metric_frame import MEAN_GROUP_ID

if TYPE_CHECKING:
    from views_evaluation.evaluation.metric_frame import MetricFrame


class AmbiguousMetric(ValueError):
    """More than one mean row matches a single (eval_type, target, metric).

    A value cannot be chosen without guessing; the caller renders a visible
    "ambiguous" cell rather than a possibly-wrong number (register C-116; ADR-008).
    """


def mean_metric_value(
    frame: "MetricFrame", *, eval_type: str, target: str, metric: str
) -> Optional[float]:
    """The cross-group mean value for ``(eval_type, target, metric)``.

    Reads the ``group_id="mean"`` aggregate row that views-evaluation emits for the
    consumer to match on. Returns:

    - ``None`` — no matching mean row, or the value is NaN ("not calculated").
    - ``float`` — the unique matching value.
    - raises :class:`AmbiguousMetric` — more than one mean row matches (C-116).
    """
    ids = frame.identifiers
    mask = (
        (ids["eval_type"] == eval_type)
        & (ids["target"] == target)
        & (ids["metric"] == metric)
        & (ids["group_id"] == MEAN_GROUP_ID)
    )
    matched = frame.values[mask]
    if matched.shape[0] == 0:
        return None
    if matched.shape[0] > 1:
        raise AmbiguousMetric(
            f"{matched.shape[0]} mean rows match (eval_type={eval_type!r}, "
            f"target={target!r}, metric={metric!r}); a single value cannot be "
            "chosen without guessing (register C-116)."
        )
    value = float(matched[0, 0])
    return None if math.isnan(value) else value


def unique_axis_value(frame: "MetricFrame", axis: str) -> Optional[str]:
    """The single distinct value of ``axis`` across the frame, or ``None`` if the
    frame is empty. Raises ``ValueError`` if the axis is not uniform — a frame for one
    evaluation must carry one ``level``/``partition`` (the cross-constituent
    consistency guard reads these)."""
    values = np.unique(frame.identifiers[axis])
    if values.shape[0] == 0:
        return None
    if values.shape[0] > 1:
        raise ValueError(
            f"Axis {axis!r} is not uniform across the frame: {list(values)}"
        )
    return str(values[0])
