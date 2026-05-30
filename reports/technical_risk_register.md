# Technical Risk Register

**Last updated:** 2026-05-30
**Governing ADR:** ADR-010 (Technical Risk Register)
**Entry count:** 10 concerns (7 resolved) + 0 disagreements

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

### C-03: Test coverage — all 8 CIC classes covered, depth varies

| Field | Value |
|-------|-------|
| ID | C-03 |
| Tier | 4 |
| Source | repo-assimilation (2026-05-29), progressively addressed across 3 PRs (2026-05-29) |
| Trigger | When a developer adds a new CIC-governed class without accompanying tests |
| Location | `tests/` (151 passing in views_pipeline env) |

All 8 CIC-governed classes now have test coverage. 151 tests pass in the `views_pipeline` conda env. Coverage depth varies: PDA and ForecastReconciler have full red/green/beige suites; the remaining 6 classes have validation + smoke tests. Some tests skip in environments without `views_pipeline_core`. Remaining depth gaps (green/beige team for visualization and mapping classes) are tracked on GitHub issue #2 as incremental improvements, not blocking risks. Downgraded from Tier 2 to Tier 4.

---

### C-09: Template classes lack CICs

| Field | Value |
|-------|-------|
| ID | C-09 |
| Tier | 4 |
| Source | repo-assimilation (2026-05-29) |
| Trigger | When a developer modifies `EvaluationReportTemplate` or `ForecastReportTemplate` without understanding the pipeline-core reporting contract |
| Location | `views_reporting/templates/reports/evaluation.py`, `views_reporting/templates/reports/forecast.py` |

`EvaluationReportTemplate` and `ForecastReportTemplate` are non-trivial classes per ADR-006 criteria (orchestrate multiple components, enforce semantic invariants on report structure). They were added in the PR 6 companion commit but lack intent contracts. ADR-006 mandates CICs for such classes. No tests exist in this repo — test coverage lives in pipeline-core's `test_reporting_stage.py`.

---

### C-10: Transform-detection logic in reconciliation assumes retired prefix convention

| Field | Value |
|-------|-------|
| ID | C-10 |
| Tier | 3 |
| Source | repo-assimilation + graphify analysis (2026-05-30) |
| Trigger | When the platform fully retires the `ln_`/`lx_`/`lr_` prefix convention from model target names and views-reporting still contains prefix-sniffing code that misleads developers about data scale expectations |
| Location | `views_reporting/reconciliation/dataset_export.py:63-76,134-147`, `views_reporting/transformations/transformations.py` (entire module) |

`to_reconciler()` and `reconcile_pg_dataset()` in `dataset_export.py` detect `ln`/`lx` in feature names via `feature.split("_")` and apply inverse/forward log transforms. All 56+ production models use `lr_` (linear/raw) targets, meaning these branches never execute. The logic couples views-reporting to a naming convention the platform has retired. `DatasetTransformationModule` (1,494 LOC) implements the full `ln_`/`lx_`/`lr_` lifecycle but has zero production callers. Per stakeholder direction, this repo should expect data on its original measurement scale and not infer or reverse transformations. Governed by ADR-011.

See also C-04 (resolved — offset hardcoding in the same transform logic).

---

## Disagreements

| ID | Narrative | Positions | Status |
|----|-----------|-----------|--------|

---

## Resolved Concerns

### C-08: Unused templates package — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-08 |
| Resolved | 2026-05-29 |
| Resolution | Templates populated with `EvaluationReportTemplate` and `ForecastReportTemplate` in the PR 6 companion commit (`2996523`). Package is no longer empty. |

---

### C-07: Duplicate search_for_item_name functions — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-07 |
| Resolved | 2026-05-29 |
| Resolution | Deleted `search_for_item_name2` (identical to `search_for_item_name`). Updated `filter_metrics_by_eval_type_and_metrics()` to call the surviving function. Removed re-export from `reports/__init__.py`. |

---

### C-06: ForecastReconciler accepts dead optimization parameters — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-06 |
| Resolved | 2026-05-29 |
| Resolution | Removed `lr`, `max_iters`, `tol` from `reconcile_forecast()`, `ReconciliationModule.reconcile()`, and `_reconcile_country_worker()`. Parameters were accepted but never used — actual algorithm is proportional scaling. No callers passed custom values. |

---

### C-05: HistoricalLineGraph crashes in forecast-only mode — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-05 |
| Resolved | 2026-05-29 |
| Resolution | Added `_resolved_time_id` property that falls back to `forecast_dataset._time_id` when `historical_dataset` is None. Replaced 6 unguarded `self.historical_dataset._time_id` accesses in `_create_hdi_traces`, `_create_historical_trace`, `_create_forecast_trace`, and `_format_interactive_plot`. Deleted dead `_get_plot_data()` method. Verified HDI bands render in forecast-only mode without silent error swallowing. |

---

### C-04: undo_all_transformations() hardcodes lx offset — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-04 |
| Resolved | 2026-05-29 |
| Resolution | Added `_lookup_lx_offset()` helper that reads offset from `transformation_history`. Fixed both `undo_all_transformations()` (line 1304) and `undo_transformations()` (line 1454) to use it. Verified with near-zero test data where `exp(-50)` vs `exp(-100)` produces visible corruption. |

---

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
