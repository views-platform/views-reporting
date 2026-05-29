# Technical Risk Register

**Last updated:** 2026-05-29
**Governing ADR:** ADR-010 (Technical Risk Register)
**Entry count:** 8 concerns (2 resolved) + 0 disagreements

---

## Tier Definitions

| Tier | Severity | Criteria |
|------|----------|----------|
| 1 | Critical | Silent data corruption or model output incorrectness. No error signal. Requires immediate attention. |
| 2 | High | Structural fragility that will cause failures under realistic change scenarios. Clear trigger exists. |
| 3 | Medium | Maintainability or coupling issues that increase cost of change. Multiple developers affected. |
| 4 | Low | Code quality observations. Single-developer scope. No correctness or reliability impact. |

---

## Open Concerns

### C-03: Low pytest test coverage (46 CIC guarantees untested)

| Field | Value |
|-------|-------|
| ID | C-03 |
| Tier | 2 |
| Source | repo-assimilation (2026-05-29), qualified by test-review (2026-05-29) |
| Trigger | When any developer modifies a transformation, reconciliation, mapping, or visualization function and relies on CI to catch regressions |
| Location | `tests/` (13 tests covering `PosteriorDistributionAnalyzer` only) |

Test-review against 8 CICs found 10 of 56 CIC guarantees tested (18%). Only `PosteriorDistributionAnalyzer` has coverage (13 tests: 2 red, 7 green, 2 beige). Per-class breakdown of untested guarantees:

- **ForecastReconciler** (0/5): sum constraint, zero preservation, shape preservation, format detection, non-negativity. 15 inline test cases exist in `run_tests_probabilistic()`/`run_tests_point()` — harvest into pytest.
- **DatasetTransformationModule** (0/6): forward transforms, round-trip recovery, column mapping, history tracking, duplicate detection, column validation. Round-trip tests would have caught C-04.
- **ReconciliationModule** (0/5): type validation, temporal alignment, target intersection, parallel correctness, result application.
- **MappingModule** (0/5): shapefile dispatch, geometry prep, data-geometry merge, interactive maps, static maps.
- **HistoricalLineGraph** (0/5): dataset acceptance, both-None ValueError, HDI bands, dropdown, forecast-only mode (C-05).
- **ReportModule** (0/5): content accumulation, header embedding, table splitting, image base64, HTML export.
- **PlotDistribution** (0/4): MAP+HDI overlay, multiple HDI levels, invalid variable ValueError, empty data handling.
- **PosteriorDistributionAnalyzer** (10/11): missing only input validation (ValueError on invalid credible_masses, threshold, bins).

---

### C-04: undo_all_transformations() hardcodes lx offset

| Field | Value |
|-------|-------|
| ID | C-04 |
| Tier | 2 |
| Source | repo-assimilation (2026-05-29) |
| Trigger | When a caller invokes `lx_transform(columns, offset=-50)` (or any non-default offset) and later calls `undo_all_transformations()` |
| Location | `views_reporting/transformations/transformations.py:1298` |

`undo_all_transformations()` hardcodes `offset = -100` when reversing `lx` transforms. The offset used in the original `lx_transform()` call is stored in `self.transformation_history` but is never consulted during the bulk undo. If a caller applied `lx_transform()` with `offset=-50`, the undo computes `exp(x) - exp(-100)` instead of `exp(x) - exp(-50)`, silently producing incorrect values. The per-column `undo_lx_transform()` also defaults to `-100` but at least accepts an explicit offset parameter.

See also C-02 (related lx offset inconsistency).

---

### C-05: HistoricalLineGraph crashes in forecast-only mode

| Field | Value |
|-------|-------|
| ID | C-05 |
| Tier | 2 |
| Source | repo-assimilation (2026-05-29) |
| Trigger | When a caller creates `HistoricalLineGraph(historical_dataset=None, forecast_dataset=ds)` and calls `plot_predictions_vs_historical()` with HDI enabled |
| Location | `views_reporting/visualizations/historical.py:415`, `views_reporting/visualizations/historical.py:360-374` |

The constructor accepts `historical_dataset=None`, but `_create_hdi_traces()` at line 415 unconditionally accesses `self.historical_dataset._time_id` to index the HDI DataFrame columns. This raises `AttributeError` when `historical_dataset` is `None`. The `_get_plot_data()` method at line 360 also accesses both datasets unconditionally. The `plot_predictions_vs_historical()` method logs a warning about missing historical data but does not prevent the code path from reaching these unguarded accesses.

---

### C-06: ForecastReconciler accepts dead optimization parameters

| Field | Value |
|-------|-------|
| ID | C-06 |
| Tier | 3 |
| Source | repo-assimilation (2026-05-29) |
| Trigger | When a developer adjusts `lr`, `max_iters`, or `tol` in `ReconciliationModule.reconcile()` expecting optimization behavior to change |
| Location | `views_reporting/statistics/statistics.py:560-563` |

`ForecastReconciler.reconcile_forecast()` accepts `lr`, `max_iters`, and `tol` parameters but never uses them — the actual algorithm is simple proportional scaling. The docstring notes "(currently unused)" but `ReconciliationModule.reconcile()` passes these values through, and a developer tuning reconciliation performance could waste significant time adjusting parameters that have no effect. This API mismatch between signature and behavior affects anyone working on reconciliation.

---

### C-07: Duplicate search_for_item_name functions

| Field | Value |
|-------|-------|
| ID | C-07 |
| Tier | 4 |
| Source | repo-assimilation (2026-05-29) |
| Trigger | When a developer fixes a bug or changes behavior in one of the two functions without updating the other |
| Location | `views_reporting/reports/utils.py:60-104`, `views_reporting/reports/utils.py:106-152` |

`search_for_item_name` and `search_for_item_name2` are functionally identical — both use the same regex-based discrete-segment matching logic with the same warning behavior. Both are exported from `reports/__init__.py` and used by `filter_metrics_by_eval_type_and_metrics()`. Any behavior change or bug fix must be applied to both functions independently.

---

### C-08: Unused templates package

| Field | Value |
|-------|-------|
| ID | C-08 |
| Tier | 4 |
| Source | repo-assimilation (2026-05-29) |
| Trigger | When a developer searches for report template functionality and encounters the empty package |
| Location | `views_reporting/templates/__init__.py`, `views_reporting/templates/reports/__init__.py` |

The `templates/` and `templates/reports/` packages contain only empty `__init__.py` files. No module in the repository imports from them. They appear to be scaffolding from the extraction from `views-pipeline-core` that was never populated. Their presence creates false expectations about template functionality.

---

## Disagreements

| ID | Narrative | Positions | Status |
|----|-----------|-----------|--------|

---

## Resolved Concerns

### C-02: Wrong sign in lx untransform in dataset_export.py — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-02 |
| Resolved | 2026-05-29 |
| Resolution | Fixed `np.exp(100)` → `np.exp(-100)` in `to_reconciler()` at `dataset_export.py:69` before initial commit. Shipped in commit `1f49fab` (PR 8). |

---

### C-01: Thread-unsafe shared PosteriorDistributionAnalyzer singleton — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-01 |
| Resolved | 2026-05-29 |
| Resolution | Refactored `_compute_summary()` to accept parameters instead of reading `self.*` (Layer 1), deleted module-level `_analyzer` singleton and replaced with per-call instantiation in all three helpers (Layer 2). Verified by 9 tests across red/green/beige categories per ADR-005. |

---

## Register Conventions

Concerns are registered via the `register-risk` skill and curated via the `review-rr` skill.

- **C-xx:** Concern entries (technical risks, code quality issues, architectural debt)
- **D-xx:** Disagreement entries (unresolved debates between expert perspectives)

Concerns are closed when:
- The underlying issue is resolved (code change merged)
- The risk is formally accepted with documented rationale
- The concern is superseded by a different approach
