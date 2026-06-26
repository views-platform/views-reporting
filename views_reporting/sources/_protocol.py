"""EvaluationSource protocol: the injected port the eval report renders from."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol

if TYPE_CHECKING:
    from views_evaluation.evaluation.metric_frame import MetricFrame

    from views_reporting.sources.evaluation_provenance import EvaluationProvenance


class EvaluationSource(Protocol):
    """Supplies the evaluation-of-record — a typed ``MetricFrame`` — for the report
    to render, instead of the report acquiring metrics itself (ADR-018).

    The render code depends on this interface, never on where the data comes from
    (file, store, or — transitionally — a WandB scrape). Implementations handle one
    source each (SRP); a new source is a new class, not a change here (OCP). New
    sources are injected by the caller, not dispatched by a format token, so there is
    deliberately no registry (unlike ``loaders/``). ``views_evaluation`` is imported
    only under TYPE_CHECKING so the port stays import-light (SDP/SAP — stable + abstract).

    A source is bound to one ``target`` at construction (a report is per-target), so
    only the ``model`` varies across calls and ``provenance()`` can locate the subject
    evaluation without a target argument.

    Failure taxonomy (the #105/#177 contract the report relies on):

    - ``metric_frame`` returns ``None`` -> **absent**: no evaluation exists for this
      model. The report degrades-and-announces (does not drop silently).
    - ``metric_frame`` raises -> **transient**: a retrieval hiccup. The report retries
      once, then marks the model degraded.
    """

    def metric_frame(self, model: str) -> Optional["MetricFrame"]:
        """The MetricFrame for one model (at the bound target), or ``None`` if absent."""
        ...

    def provenance(self) -> "EvaluationProvenance":
        """Identity of the evaluation being reported (for the header + footer)."""
        ...
