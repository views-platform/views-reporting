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
# These are real `views_evaluation` metric tokens (see its `metric_catalog.py`
# METRIC_CATALOG / METRIC_MEMBERSHIP), reconciled with the ensemble governance
# protocol ADR-029 (point: MSLE, MSE, conservativeness; probabilistic: CRPS, MIS,
# Log Score=Ignorance, conservativeness). Two constraints on the names
# (see ADR-017, risk C-41):
#   1. They must match the metric tokens the evaluator emits into the WandB run
#      summary, or they always read as "not calculated".
#   2. No name may be a `/_-`-bounded *segment-prefix* of another within a cell
#      (e.g. "Brier_cls_point" vs "Brier_cls_sample"), else `search_for_item_name`
#      would mis-match. ("CRPS" vs "twCRPS" is safe — the boundary rule blocks it.)
# Pending decisions (kept "for now"): conservativeness uses MCR (the more
# interpretable calibration ratio) AND keeps `y_hat_bar` until HH confirms;
# ensemble **diversity** (ADR-029 Rule 2) is intentionally OMITTED — its evaluator
# metric `SD` is `implemented=False` upstream, so it cannot be reported yet (gap
# owned by views_evaluation, not this repo). Classification is sparse upstream:
# the cells below are the full *implemented* membership.
_CANONICAL_REPORT_METRICS: "Mapping[tuple[str, str], tuple[str, ...]]" = MappingProxyType(
    {
        ("regression", "point"): ("MSLE", "MSE", "MCR_point", "y_hat_bar"),
        ("regression", "sample"): ("CRPS", "MIS", "Ignorance", "MCR_sample", "y_hat_bar"),
        ("classification", "point"): ("AP", "Brier_cls_point"),
        ("classification", "sample"): ("Brier_cls_sample", "CRPS"),
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
        max_map_cells: Upper bound on the number of rendered map entries (entities
            × time steps) a choropleth may build before the renderer fails loud
            rather than risk an out-of-memory failure or a multi-GB HTML file
            (register C-26). The count is the real size/memory driver; as a coarse
            calibration, a single-origin PGM map is ≈86 MB at ~13k cells, and a
            full global PRIO-GRID grid is ~260k cells. Defaults to ``50_000`` — well
            above realistic Africa+Middle-East subsets (a few origins of ~13k
            cells) but below the full-global grid. Raise it deliberately when a
            large render is genuinely intended. Injected into ``MappingModule`` at
            the Compose boundary (ADR-016); the Render layer never reads config.
        pgm_raster: Opt-in (declared, ADR-003) to render PGM maps as a bounded
            **raster heatmap** over the grid lattice instead of a vector choropleth
            (register C-26 / #125). The raster embeds no polygon geometry, so it
            renders the full PRIO-GRID grid within the report's byte budget and is
            exempt from ``max_map_cells``. Default ``False`` — existing choropleth +
            fail-loud guard unchanged; set ``True`` to enable large-grid PGM maps.
            CM is not a lattice, so this affects PGM only.
        canonical_report_metrics: The metrics the evaluation report attempts to
            show, keyed by ``(task, pred_type)`` for every cell of
            ``{regression, classification} × {point, sample}``.
    """

    hdi_levels: tuple[float, ...] = (0.9, 0.95, 0.99)
    default_hdi_level: float = 0.9
    max_map_cells: int = 50_000
    pgm_raster: bool = False
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
        if not isinstance(self.max_map_cells, int) or self.max_map_cells <= 0:
            raise ValueError(
                f"max_map_cells must be a positive integer; got {self.max_map_cells!r}."
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
