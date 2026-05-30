# Technical Risk Register

**Last updated:** 2026-05-30
**Governing ADR:** ADR-010 (Technical Risk Register)
**Entry count:** 15 concerns (7 resolved) + 5 disagreements

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

**Latent silent corruption risk (FM-9):** If a future model or experiment names its target `pred_ln_ged_sb` (naming accident, copy-paste from old configs), `to_reconciler()` would silently apply `exp(data) - 1` to data that was NOT log-transformed, producing silently wrong reconciliation results consumed by decision-makers. No error, no warning. The only mitigation is deleting the branches.

**Concrete removal plan:** Delete 4 `if`/`elif` blocks (lines 63-76, 134-147) and 3 `else` DEBUG logs (lines 74-76, 144-147) from `dataset_export.py`. 34 lines deleted, 0 added. No test changes needed — the integration test uses `pred_ged_sb` which always takes the `else` path. `DatasetTransformationModule` disposition deferred per ADR-001 (Legacy).

See also C-04 (resolved — offset hardcoding in the same transform logic).

---

### C-11: Silent HDI degradation in HistoricalLineGraph

| Field | Value |
|-------|-------|
| ID | C-11 |
| Tier | 3 |
| Source | expert-review (2026-05-30) |
| Trigger | When `_get_hdi_data()` or `_create_hdi_traces()` fails for a specific entity due to degenerate data (too few samples, all-NaN, numerical instability), and the user sees a clean line graph without uncertainty bands |
| Location | `views_reporting/visualizations/historical.py:247-256` |

The `except Exception` block at line 247 catches any failure in HDI computation or trace creation, logs it as ERROR, and silently falls back to a simple forecast trace without HDI bands. The user sees a clean line graph and has no way to know that uncertainty information was computed but failed — they may interpret the absence of bands as model confidence rather than computation failure. Per ADR-008, structural failures must not be silently swallowed. The plot should include a visible annotation when HDI bands are dropped.

See also C-05 (resolved — the `None` dataset crash that was one specific cause of this broader pattern).

---

### C-12: Redundant pre-sort and misleading alpha in calculate_map

| Field | Value |
|-------|-------|
| ID | C-12 |
| Tier | 4 |
| Source | expert-review (2026-05-30) |
| Trigger | When a developer passes `alpha=0.5` to `calculate_map()` expecting it to affect the MAP estimate, or when profiling reveals the pre-sort as a performance bottleneck on large datasets |
| Location | `views_reporting/statistics/dataset_statistics.py:438,477` |

Two code quality issues in `calculate_map()`: (1) Line 477 pre-sorts the entire 4D tensor (`np.sort(tensor, axis=2)`) before per-cell iteration, but each cell's samples are sorted again inside `_compute_summary()` at `statistics.py:200` — the pre-sort is wasted work. (2) The `alpha` parameter (line 438) controls HDI credibility level, not the MAP estimate — MAP is the histogram mode regardless of alpha. The parameter exists because `_compute_single_map` calls `analyze()` which always computes both MAP and HDI, but from the caller's perspective it's misleading.

---

### C-13: Cross-module private import from visualizations to statistics

| Field | Value |
|-------|-------|
| ID | C-13 |
| Tier | 4 |
| Source | expert-review (2026-05-30) |
| Trigger | When `_calculate_single_hdi` or `_compute_single_map` is renamed, moved, or refactored in `dataset_statistics.py`, requiring a coordinated change in `distributions.py` |
| Location | `views_reporting/visualizations/distributions.py:8-11` |

`PlotDistribution` imports `_calculate_single_hdi` and `_compute_single_map` (underscore-prefixed, conventionally private) from `dataset_statistics.py`. This crosses the statistics→visualization module boundary with a private API. The functions add only NaN checking over `PosteriorDistributionAnalyzer().analyze()` — NaN filtering that `PlotDistribution` already does at line 68. Either promote the functions to public API (remove underscore, add to `__init__.py`) or have `PlotDistribution` use the public dataset-level API (`calculate_hdi`/`calculate_map`) directly.

---

### C-14: WandB alerts ignore wandb_notifications flag

| Field | Value |
|-------|-------|
| ID | C-14 |
| Tier | 3 |
| Source | expert-review (2026-05-30) |
| Trigger | When a caller sets `wandb_notifications=False` in a CI pipeline or test environment where WandB is configured with a webhook, and error/completion alerts still fire to production channels |
| Location | `views_reporting/reconciliation/reconciliation.py:256-260,286-289` |

The init alert at line 110 correctly passes `notifications_enabled=self._wandb_notifications`. The failure alert at line 256 and completion alert at line 286 omit this parameter, meaning they always attempt to fire regardless of the flag. In environments where `wandb.run` is active (CI pipelines, staging), this sends unintended alerts. Two-line fix: add `notifications_enabled=self._wandb_notifications` to both calls.

---

### C-15: Dead self._reconciler instance in ReconciliationModule

| Field | Value |
|-------|-------|
| ID | C-15 |
| Tier | 4 |
| Source | expert-review (2026-05-30) |
| Trigger | When a developer modifies `self._reconciler` configuration expecting it to affect reconciliation behavior |
| Location | `views_reporting/reconciliation/reconciliation.py:72` |

`self._reconciler = ForecastReconciler(device=self._device)` is created in `__init__` but never referenced by `reconcile()` or any other method. Each worker creates its own `ForecastReconciler` at line 167. A developer could waste time configuring this instance without realizing the workers ignore it. One-line fix: delete line 72.

---

## Disagreements

### D-06: Private import vs. public API for single-cell statistical helpers

| Field | Value |
|-------|-------|
| ID | D-06 |
| Source | expert-review (2026-05-30) |
| Perspectives | **Feathers** (promote to public API — remove underscore, make the import legitimate) vs. **Martin/Ousterhout** (eliminate the import — PlotDistribution should use dataset-level API or PosteriorDistributionAnalyzer directly) vs. **Hickey** (PlotDistribution shouldn't compute at all — receive pre-computed data) |
| Resolution | Unresolved — simplest fix is Feathers' rename; cleanest architecture is Martin's dataset-level API |

---

### D-07: Should PlotDistribution compute its own statistics or receive pre-computed data?

| Field | Value |
|-------|-------|
| ID | D-07 |
| Source | expert-review (2026-05-30) |
| Perspectives | **Hickey** (PlotDistribution should only render — computation is a separate concern) vs. **Beck** (current design is the simplest thing that works — 3 lines of computation inside the renderer is fine) vs. **Ousterhout** (dataset_statistics should provide a visualization-preparation function) |
| Resolution | Unresolved — depends on whether computation-free rendering is a real use case |

---

### D-08: Should reconciliation workers receive DataFrames or pre-extracted tensors?

| Field | Value |
|-------|-------|
| ID | D-08 |
| Source | expert-review (2026-05-30) |
| Perspectives | **Kleppmann** (extract tensors in main process, send only tensors — eliminates dataset reconstruction, transform detection, and pipeline-core imports in workers) vs. **Beck** (current design works and is tested — pre-extraction adds complexity to main loop) vs. **Feathers** (current design is untestable without pipeline-core — moving extraction out improves testability) |
| Resolution | Unresolved — Kleppmann's approach aligns with ADR-011 and simplifies workers, but requires main-loop restructuring |

---

### D-09: Should reconcile() return a value or mutate in-place?

| Field | Value |
|-------|-------|
| ID | D-09 |
| Source | expert-review (2026-05-30) |
| Perspectives | **Feathers** (return new DataFrame, don't mutate — makes partial failure recoverable) vs. **Nygard** (mutation is existing contract — but add partial-failure signal to return) vs. **Hickey** (mutation is place-oriented anti-pattern — return a value, let caller decide) |
| Resolution | Unresolved — current API does both (mutates AND returns), which is the worst option; should commit to one |

---

### D-10: Is ADR-011 correctly classified as project-specific?

| Field | Value |
|-------|-------|
| ID | D-10 |
| Source | expert-review (2026-05-30) |
| Perspectives | **Hickey** (ADR-011 overrides a constitutional category in ADR-001 — it should be constitutional or acknowledged as having constitutional-level impact) vs. **Beck** (should have been an amendment to ADR-003, not a separate ADR — inflates the governance stack) vs. **Martin** (the distinction holds — ADR-011 doesn't change how governance works, only what the repo expects as input) |
| Resolution | Unresolved — pragmatic resolution: keep as project-specific but update README to note constitutional-level implications, and update ADR-001's Data Transformation category |

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
