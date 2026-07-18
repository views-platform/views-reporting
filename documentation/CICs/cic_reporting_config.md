
# Class Intent Contract: ReportingConfig

**Status:** Active
**Owner:** views-reporting maintainers
**Last reviewed:** 2026-07-18 (created — governance-drift round; ADR-006 "enforces invariants" + ADR-009 "configuration validation" triggers)
**Related ADRs:** ADR-003 (declarations over inference), ADR-008 (fail-loud), ADR-009 (boundary/config validation), ADR-016 (repository configuration mechanism), ADR-017 (canonical metrics), ADR-018 render-ladder addendum

---

## 1. Purpose

`ReportingConfig` is the repo's single, frozen configuration boundary (ADR-016): a validated,
immutable dataclass holding every declared rendering/reporting parameter. It exists so that
**only the Compose layer reads configuration** — templates read it once per report and inject
plain values downward; Render-layer classes never import it.

## 2. Non-Goals

- Not a runtime-mutable settings object (frozen dataclass; the module-level singleton is built
  once by `get_config()`).
- Not an environment/CLI parser — values are code-declared defaults (ADR-003), changed by
  editing the dataclass, not by ambient state.
- Not a home for per-report options — those are `generate()` arguments.

## 3. Responsibilities and Guarantees

- **Fields (the declared surface):** `hdi_levels` (default `(0.9, 0.95, 0.99)`),
  `default_hdi_level` (`0.9`), `max_map_cells` (`50_000` — the choropleth fail-loud guard,
  C-26), `pgm_raster` (`False` — declared raster override, ADR-003),
  `max_raster_cell_frames` (`2_000_000` **uniform-lattice cell-frames** — the raster budget,
  C-203/C-208/C-209; recalibrated 2026-07-15 at ~34 B/cf measured), and
  `canonical_report_metrics` (the ADR-017 canonical-metric standard keyed by
  `(task, pred_type)`).
- **Fail-loud validation (`__post_init__`, ADR-008):** every HDI level in `(0, 1)`;
  `default_hdi_level` must be one of `hdi_levels`; `max_map_cells` and
  `max_raster_cell_frames` must be positive integers; invalid values raise `ValueError` at
  construction — a misconfigured repo cannot render at all.
- **Immutability:** `frozen=True`; consumers cannot mutate shared state.

## 4. Inputs and Assumptions

None at call time — `get_config()` takes no arguments and returns the singleton. Field-default
changes are code changes reviewed like any other (their docstrings carry the calibration
evidence and register IDs).

## 5. Outputs and Side Effects

`get_config() -> ReportingConfig`. No I/O, no logging, no mutation.

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| Any HDI level outside (0,1); default not in levels | `ValueError` at construction | `__post_init__` |
| Non-positive / non-int `max_map_cells` or `max_raster_cell_frames` | `ValueError` at construction | `__post_init__` |

## 7. Boundaries and Interactions

Read by the two report templates (Compose layer) only; values injected into
`MappingModule.plot_map(...)` and `HistoricalLineGraph.plot_predictions_vs_historical(...)` as
plain arguments. **Render/Computation layers must not import this module** (ADR-016) — the
render ladder's budget quantities travel as parameters.

## 8. Examples of Correct Usage

```python
from views_reporting.config import get_config

cfg = get_config()  # in a template's generate() only
html = mapper.plot_map(mdf, target, interactive=True, as_html=True,
                       max_cells=cfg.max_map_cells,
                       raster=use_raster,
                       max_raster_cell_frames=cfg.max_raster_cell_frames)
```

## 9. Examples of Incorrect Usage

```python
# WRONG: reading config inside a Render-layer class (ADR-016)
from views_reporting.config import get_config  # inside mapping.py — forbidden

# WRONG: mutating the singleton
get_config().max_map_cells = 10**9  # FrozenInstanceError
```

## 10. Test Alignment

`tests/test_config.py` (12 tests: defaults, frozen-ness, every `__post_init__` raise);
budget semantics exercised end-to-end in `tests/test_forecast_raster_select.py`,
`tests/test_global_scale.py`, `tests/test_sample_scale.py`.

## 11. Evolution Notes

Budget defaults are **calibration facts** — each change must re-measure and update the field
docstring (precedent: the C-209 recalibration 1M → 2M with 34 B/cf evidence). The
`canonical_report_metrics` mapping is governed by ADR-017; additions land there first.

---

## End of Contract

This document defines the **intended meaning** of `ReportingConfig`.
Changes to behavior that violate this intent are bugs.
Changes to intent must update this contract.
