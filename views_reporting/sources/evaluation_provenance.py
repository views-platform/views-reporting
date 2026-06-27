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
    frame metadata. ``run_url``/``owner`` are generic optional fields no current source
    populates (the WandB scrape that once filled them is gone, B2 / C-108); they remain
    so a future source that has a run link can render it without a DTO change.
    """

    run_id: str
    run_url: Optional[str] = None
    owner: Optional[str] = None
    run_date: Optional[str] = None
    data_version: Optional[str] = None
    scoring_code_version: Optional[str] = None
