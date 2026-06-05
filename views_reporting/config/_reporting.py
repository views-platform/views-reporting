"""Default reporting configuration: the in-package source of report/plot defaults.

This is the repository's first configuration primitive. Today the only "config"
in views-reporting is the per-run ``dict`` the caller (pipeline-core) threads into
the report templates; that describes *what to report*. This module instead holds
views-reporting's *own* rendering defaults — values that previously lived hardcoded
deep in plotting code.

It is intentionally a Python module (not a YAML/TOML file): zero new dependency,
type-safe, and it ships inside the wheel so ``pip install views-reporting`` users
get the defaults out of the box.

Scope note: this scaffolding seeds **only** the HDI credible levels. Other
hardcoded values (colours, figure heights, opacities, map quantiles) are
candidates to migrate here later. Consumers should read values through
:func:`get_config` rather than importing fields directly, so the backing store can
evolve (caller overrides, a file) without touching call sites.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportingConfig:
    """Immutable container for views-reporting's rendering defaults.

    Attributes:
        hdi_levels: Precomputed Highest Density Interval credible levels a reader
            may select between in the historical line graph, as credible masses in
            ``(0, 1)`` (e.g. ``0.9`` == 90% HDI).
        default_hdi_level: The level shown when none is chosen. Must be one of
            ``hdi_levels``. Defaults to ``0.9``, matching the previously hardcoded
            behaviour so wiring this in later is behaviour-preserving.
    """

    hdi_levels: tuple[float, ...] = (0.9, 0.95, 0.99)
    default_hdi_level: float = 0.9

    def __post_init__(self) -> None:
        # Fail loud on incoherent config (ADR-008): catch mistakes at construction,
        # not silently downstream in a plot.
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


_CONFIG = ReportingConfig()


def get_config() -> ReportingConfig:
    """Return the active reporting configuration.

    The accessor seam: reporting code should call this rather than importing
    defaults directly, so the source of config can later change (caller overrides,
    an external file) without changing call sites.
    """
    return _CONFIG
