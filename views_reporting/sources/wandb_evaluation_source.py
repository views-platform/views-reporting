"""WandbEvaluationSource: INTERIM EvaluationSource that scrapes WandB into MetricFrames.

This is the swappable leaf that keeps the eval report working while pipeline-core has
no MetricFrame producer (#218). It absorbs the WandB scrape (`format_evaluation_dict`)
and the metric-aware constituent run selection (`evaluation_run_resolver`) that used to
live in the template, presenting them behind the `EvaluationSource` port. **Deleted in
B2** (C-108) once pipeline-core persists frames and its reporting stage injects a
`MetricFrameFileSource`. No new render-time WandB coupling lives in the template.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

import numpy as np
from views_evaluation.evaluation.metric_frame import AXES, MEAN_GROUP_ID, MetricFrame
from views_pipeline_core.modules.wandb import (
    format_evaluation_dict,
    format_metadata_dict,
    timestamp_to_date,
)

from views_reporting.config import get_config
from views_reporting.reports.utils import find_item_names
from views_reporting.sources.evaluation_provenance import EvaluationProvenance
from views_reporting.templates.reports.evaluation_run_resolver import (
    Resolution,
    resolve_constituent_run,
)

# Active {task}×{pred_type} cell → its config key (ADR-017). The canonical metric
# universe to extract is the union over cells the config activates.
_CELL_KEYS = {
    ("regression", "point"): "regression_point_metrics",
    ("regression", "sample"): "regression_sample_metrics",
    ("classification", "point"): "classification_point_metrics",
    ("classification", "sample"): "classification_sample_metrics",
}


class WandbEvaluationSource:
    """Builds a ``MetricFrame`` per model from a WandB scrape, bound to one target.

    The primary model uses the injected ``wandb_run``; constituents are resolved
    metric-aware via ``evaluation_run_resolver`` (absent → ``None``; transient → raise,
    preserving the #105/#177 contract the template relies on).
    """

    def __init__(
        self,
        wandb_run,
        *,
        run_type: str,
        config: Dict,
        target: str,
        primary_model: str,
        eval_types: List[str],
    ):
        self._run = wandb_run
        self._run_type = run_type
        self._config = config
        self._target = target
        self._primary_model = primary_model
        self._eval_types = eval_types or ["time-series-wise"]
        self._canonical_metrics = self._canonical_universe()

    def _canonical_universe(self) -> Set[str]:
        active = [c for c, key in _CELL_KEYS.items() if self._config.get(key)]
        cfg = get_config()
        return {m for cell in active for m in cfg.canonical_metrics(*cell)}

    def _resolve_run(self, model: str):
        if model == self._primary_model:
            return self._run
        resolution = resolve_constituent_run(
            model=model,
            run_type=self._run_type,
            target=self._target,
            eval_type=self._eval_types[0],
            canonical_metrics=self._canonical_metrics,
        )
        return resolution.run if resolution.status is Resolution.RESOLVED else None

    def metric_frame(self, model: str) -> Optional[MetricFrame]:
        run = self._resolve_run(model)
        if run is None:
            return None
        return self._build_frame(run)

    def _build_frame(self, run) -> MetricFrame:
        eval_dict = format_evaluation_dict(dict(run.summary))
        meta = format_metadata_dict(dict(run.config))
        level = str(meta.get("level", "") or "")
        partition = str(meta.get(self._run_type, "") or "")

        columns: Dict[str, list] = {axis: [] for axis in AXES}
        values: list = []
        keys = list(eval_dict.keys())
        for eval_type in self._eval_types:
            for metric in self._canonical_metrics:
                # One row PER matching key — colliding keys yield >1 mean row so the
                # ambiguity survives to mean_metric_value (C-116), never deduped here.
                for key in find_item_names(
                    keys, [eval_type, metric, self._target, "mean"]
                ):
                    try:
                        value = float(eval_dict[key])
                    except (TypeError, ValueError):
                        # A non-numeric/None summary value cannot enter a float32
                        # frame; omit the row so it renders "not calculated" rather
                        # than crashing the build.
                        continue
                    columns["eval_type"].append(eval_type)
                    columns["target"].append(self._target)
                    columns["metric"].append(metric)
                    columns["group_id"].append(MEAN_GROUP_ID)
                    columns["partition"].append(partition)
                    columns["level"].append(level)
                    values.append(value)

        values_arr = np.asarray(values, dtype=np.float32).reshape(-1, 1)
        identifiers = {axis: np.asarray(columns[axis], dtype=str) for axis in AXES}
        # Frame metadata is unused by the template on this path (provenance() reads the
        # WandB run; values/axes carry the rest), so it is left default.
        return MetricFrame(values=values_arr, identifiers=identifiers)

    def provenance(self) -> EvaluationProvenance:
        summary = dict(self._run.summary)
        ts = summary.get("_timestamp")
        owner = None
        user = getattr(self._run, "user", None)
        if user is not None:
            owner = f"{user.name} ({user.username})"
        return EvaluationProvenance(
            run_id=str(self._run.id),
            run_url=getattr(self._run, "url", None),
            owner=owner,
            run_date=timestamp_to_date(ts) if ts else None,
        )
