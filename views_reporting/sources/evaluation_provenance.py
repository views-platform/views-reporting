"""EvaluationProvenance: the presentation provenance an EvaluationSource carries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EvaluationProvenance:
    """Identity of the evaluation an EvaluationSource serves, for the report header
    and the C-34 provenance footer.

    Every field except ``run_id`` is optional and rendered with None-omission, so a
    source supplies only what it genuinely knows. The durable ``MetricFrameFileSource``
    fills ``run_id``/``run_date``/``data_version``/``scoring_code_version`` from the
    frame metadata and leaves the WandB-specific ``run_url``/``owner`` as ``None``; the
    interim ``WandbEvaluationSource`` additionally fills ``run_url``/``owner`` so the
    report keeps its clickable WandB link until the scrape is deleted (B2 / C-108).
    """

    run_id: str
    run_url: Optional[str] = None
    owner: Optional[str] = None
    run_date: Optional[str] = None
    data_version: Optional[str] = None
    scoring_code_version: Optional[str] = None
