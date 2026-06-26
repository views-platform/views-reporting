"""MetricFrameFileSource: the durable EvaluationSource — load a persisted MetricFrame."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from views_evaluation.evaluation.metric_frame import MetricFrame

from views_reporting.sources.evaluation_provenance import EvaluationProvenance


class MetricFrameFileSource:
    """Serves the evaluation-of-record by loading the ``MetricFrame`` pipeline-core
    persisted to disk (the durable Phase-3 path; ADR-018 / C-108).

    Bound to one ``target`` and ``run_type``; ``metric_frame(model)`` returns that
    model's frame or ``None`` when its directory is absent (the report then
    degrades-and-announces). A corrupt/unreadable frame propagates as transient.

    The on-disk layout is **provisional** — it must match where pipeline-core's
    producer writes frames (pipeline-core #218); pin it jointly when #218 lands.
    Unit tests construct sources over temp dirs they wrote, so this is fully testable
    before the convention is final.
    """

    def __init__(self, root: Path, run_type: str, target: str, primary_model: str):
        self._root = Path(root)
        self._run_type = run_type
        self._target = target
        self._primary_model = primary_model

    def _frame_dir(self, model: str) -> Path:
        # PROVISIONAL convention, pending pipeline-core #218.
        return self._root / model / self._run_type / f"metricframe_{self._target}"

    def metric_frame(self, model: str) -> Optional[MetricFrame]:
        directory = self._frame_dir(model)
        if not directory.is_dir():
            return None
        return MetricFrame.load(directory)

    def provenance(self) -> EvaluationProvenance:
        frame = self.metric_frame(self._primary_model)
        if frame is None:
            return EvaluationProvenance(run_id="unknown")
        meta = frame.metadata
        run_id = getattr(meta.provenance, "run_id", None)
        return EvaluationProvenance(
            run_id=str(run_id) if run_id else "unknown",
            run_date=meta.evaluation_timestamp,
            data_version=getattr(meta.provenance, "data_version", None),
            scoring_code_version=meta.scoring_code_version,
        )
