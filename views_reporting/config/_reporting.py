"""Default reporting configuration: the in-package source of report/plot defaults.

This is the repository's first configuration primitive. Today the only "config"
in views-reporting is the per-run ``dict`` the caller (pipeline-core) threads into
the report templates; that describes *what to report*. This module instead holds
views-reporting's *own* rendering defaults — values that previously lived hardcoded
deep in plotting code, plus the **canonical evaluation-report metrics standard**.

It is intentionally a Python module (not a YAML/TOML file): zero new dependency,
type-safe, and it ships inside the wheel so ``pip install views-reporting`` users
get the defaults out of the box. Consumers should read values through
:func:`get_config` rather than importing fields directly, so the backing store can
evolve without touching call sites.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

# Canonical metrics the EVALUATION report attempts to show, keyed by
# (task, pred_type). This is the central, reviewable standard owned by the
# reporting authority (ADR-017) — distinct from the per-model metric lists in
# views-models (which are dev/training choices and drive what the evaluator
# computes). A model occupies any SUBSET of these four cells (declared by which
# of its `<task>_<pred_type>_metrics` config keys are non-empty); the report
# renders the canonical metrics for each active cell and notes any the run lacks.
#
# NOTE: these seeded lists are PLACEHOLDERS pending eval-authority sign-off. Two
# constraints on the names (see ADR-017, risk C-41):
#   1. They must match the metric tokens the evaluator emits into the WandB run
#      summary (the same names used in model configs), or they always read as
#      "not calculated".
#   2. No name may be a `/_-`-bounded *segment-prefix* of another across cells
#      (e.g. "Brier_cls" vs "Brier_cls_sample"), because the report's
#      `search_for_item_name` matching would otherwise pick up the wrong key.
# Edit here to change the reporting standard.
_CANONICAL_REPORT_METRICS: "Mapping[tuple[str, str], tuple[str, ...]]" = MappingProxyType(
    {
        ("regression", "point"): ("MSLE", "MAE"),
        ("regression", "sample"): ("CRPS", "QS_sample", "MCR_sample"),
        ("classification", "point"): ("Brier_cls_point",),
        ("classification", "sample"): ("Brier_cls_sample",),
    }
)

_REQUIRED_CELLS = frozenset(_CANONICAL_REPORT_METRICS)  # the four (task, pred_type) cells


@dataclass(frozen=True)
class ReportingConfig:
    """Immutable container for views-reporting's rendering defaults + the
    canonical evaluation-report metrics standard.

    Attributes:
        hdi_levels: Precomputed Highest Density Interval credible levels a reader
            may select between in the historical line graph, as credible masses in
            ``(0, 1)`` (e.g. ``0.9`` == 90% HDI).
        default_hdi_level: The level shown when none is chosen. Must be one of
            ``hdi_levels``. Defaults to ``0.9``.
        canonical_report_metrics: The metrics the evaluation report attempts to
            show, keyed by ``(task, pred_type)`` for every cell of
            ``{regression, classification} × {point, sample}``.
    """

    hdi_levels: tuple[float, ...] = (0.9, 0.95, 0.99)
    default_hdi_level: float = 0.9
    canonical_report_metrics: "Mapping[tuple[str, str], tuple[str, ...]]" = field(
        default_factory=lambda: _CANONICAL_REPORT_METRICS
    )

    def __post_init__(self) -> None:
        # Fail loud on incoherent config (ADR-008): catch mistakes at construction,
        # not silently downstream in a plot or report.
        if not self.hdi_levels:
            raise ValueError("hdi_levels must not be empty.")
        for level in self.hdi_levels:
            if not 0.0 < level < 1.0:
                raise ValueError(
                    f"HDI levels are credible masses in (0, 1); got {level!r}."
                )
        if self.default_hdi_level not in self.hdi_levels:
            raise ValueError(
                f"default_hdi_level {self.default_hdi_level!r} must be one of "
                f"hdi_levels {self.hdi_levels!r}."
            )
        if frozenset(self.canonical_report_metrics) != _REQUIRED_CELLS:
            raise ValueError(
                "canonical_report_metrics must define exactly the cells "
                f"{sorted(_REQUIRED_CELLS)}; got {sorted(self.canonical_report_metrics)}."
            )
        for cell, metrics in self.canonical_report_metrics.items():
            if not metrics or not all(isinstance(m, str) and m for m in metrics):
                raise ValueError(
                    f"canonical_report_metrics[{cell!r}] must be a non-empty tuple "
                    "of non-empty metric names."
                )

    def canonical_metrics(self, task: str, pred_type: str) -> tuple[str, ...]:
        """Canonical report metrics for one ``(task, pred_type)`` cell (empty if unknown)."""
        return tuple(self.canonical_report_metrics.get((task, pred_type), ()))


_CONFIG = ReportingConfig()


def get_config() -> ReportingConfig:
    """Return the active reporting configuration.

    The accessor seam: reporting code should call this rather than importing
    defaults directly, so the source of config can later change (caller overrides,
    an external file) without changing call sites.
    """
    return _CONFIG
