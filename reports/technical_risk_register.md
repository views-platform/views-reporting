# Technical Risk Register

**Last updated:** 2026-05-31
**Governing ADR:** ADR-010 (Technical Risk Register)
**Entry count:** 15 concerns (12 resolved) + 5 disagreements (1 resolved)

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

### C-13: Cross-module private import from visualizations to statistics

| Field | Value |
|-------|-------|
| ID | C-13 |
| Tier | 4 |
| Source | expert-review (2026-05-30) |
| Trigger | When `_calculate_single_hdi` or `_compute_single_map` is renamed, moved, or refactored in `dataset_statistics.py`, requiring a coordinated change in `distributions.py` |
| Location | `views_reporting/visualizations/distributions.py:8-11` |

`PlotDistribution` imports `_calculate_single_hdi` and `_compute_single_map` (underscore-prefixed, conventionally private) from `dataset_statistics.py`. This crosses the statistics→visualization module boundary with a private API. Either promote the functions to public API (remove underscore, add to `__init__.py`) or have `PlotDistribution` use the public dataset-level API (`calculate_hdi`/`calculate_map`) directly.

See also D-06 (disagreement on which approach to take).

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
| Perspectives | **Kleppmann** (extract tensors in main process, send only tensors — eliminates dataset reconstruction and pipeline-core imports in workers) vs. **Beck** (current design works and is tested — pre-extraction adds complexity to main loop) vs. **Feathers** (current design is untestable without pipeline-core — moving extraction out improves testability) |
| Resolution | Unresolved — partially derisked by C-10 resolution (transform detection removed), but worker still reconstructs datasets |

---

### D-09: Should reconcile() return a value or mutate in-place?

| Field | Value |
|-------|-------|
| ID | D-09 |
| Source | expert-review (2026-05-30) |
| Perspectives | **Feathers** (return new DataFrame, don't mutate — makes partial failure recoverable) vs. **Nygard** (mutation is existing contract — but add partial-failure signal to return) vs. **Hickey** (mutation is place-oriented anti-pattern — return a value, let caller decide) |
| Resolution | Unresolved — current API does both (mutates AND returns), which is the worst option; should commit to one |

---

### D-10: Is ADR-011 correctly classified as project-specific? — RESOLVED

| Field | Value |
|-------|-------|
| ID | D-10 |
| Source | expert-review (2026-05-30) |
| Perspectives | **Hickey** (constitutional-level impact) vs. **Beck** (should be ADR-003 amendment) vs. **Martin** (distinction holds) |
| Resolution | Resolved — ADR-001 updated to mark Data Transformation as Legacy per ADR-011 (commit c4c99e9). Pragmatic path taken. |

---

## Resolved Concerns

### C-14: WandB alerts ignore wandb_notifications flag — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-14 |
| Resolved | 2026-05-31 |
| Resolution | Added `notifications_enabled=self._wandb_notifications` to failure alert (line 256) and completion alert (line 286) in `reconciliation.py`. All three `send_alert` calls now consistently respect the flag. |

---

### C-15: Dead self._reconciler instance — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-15 |
| Resolved | 2026-05-31 |
| Resolution | Deleted `self._reconciler = ForecastReconciler(device=self._device)` from `__init__`. Each worker creates its own instance; the module-level instance was never used. |

---

### C-03: Test coverage — RESOLVED (accepted)

| Field | Value |
|-------|-------|
| ID | C-03 |
| Resolved | 2026-05-31 |
| Resolution | Accepted as ongoing improvement. All 8 CIC classes have test coverage (158 tests). Remaining depth gaps tracked incrementally on GitHub issue #2. Not a blocking risk. |

---

### C-12: Redundant pre-sort and misleading alpha — RESOLVED (accepted)

| Field | Value |
|-------|-------|
| ID | C-12 |
| Resolved | 2026-05-31 |
| Resolution | Accepted as code quality backlog item. Redundant pre-sort and misleading alpha parameter have no correctness impact. May be cleaned up when `calculate_map()` is next modified. |

---

### C-10: Transform-detection logic assumes retired prefix convention — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-10 |
| Resolved | 2026-05-31 |
| Resolution | Deleted `ln`/`lx` prefix-sniffing branches from `to_reconciler()` and `reconcile_pg_dataset()` in `dataset_export.py` per ADR-011. Removed unused `numpy` import. Data now passes through on original measurement scale without inference. |

---

### C-08: Unused templates package — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-08 |
| Resolved | 2026-05-29 |
| Resolution | Templates populated with `EvaluationReportTemplate` and `ForecastReportTemplate` in the PR 6 companion commit. |

---

### C-07: Duplicate search_for_item_name functions — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-07 |
| Resolved | 2026-05-29 |
| Resolution | Deleted `search_for_item_name2`. Updated caller to use `search_for_item_name`. |

---

### C-06: ForecastReconciler accepts dead optimization parameters — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-06 |
| Resolved | 2026-05-29 |
| Resolution | Removed `lr`, `max_iters`, `tol` from entire reconciliation chain. |

---

### C-05: HistoricalLineGraph crashes in forecast-only mode — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-05 |
| Resolved | 2026-05-29 |
| Resolution | Added `_resolved_time_id` property. Replaced 6 unguarded accesses. Deleted dead `_get_plot_data()`. |

---

### C-04: undo_all_transformations() hardcodes lx offset — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-04 |
| Resolved | 2026-05-29 |
| Resolution | Added `_lookup_lx_offset()` to read offset from `transformation_history`. |

---

### C-02: Wrong sign in lx untransform — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-02 |
| Resolved | 2026-05-29 |
| Resolution | Fixed `np.exp(100)` → `np.exp(-100)` before initial commit. |

---

### C-01: Thread-unsafe PosteriorDistributionAnalyzer singleton — RESOLVED

| Field | Value |
|-------|-------|
| ID | C-01 |
| Resolved | 2026-05-29 |
| Resolution | Refactored `_compute_summary()` to pure function. Deleted singleton. Per-call instantiation. |

---

## Register Conventions

Concerns are registered via the `register-risk` skill and curated via the `review-rr` skill.

- **C-xx:** Concern entries (technical risks, code quality issues, architectural debt)
- **D-xx:** Disagreement entries (unresolved debates between expert perspectives)

Concerns are closed when:
- The underlying issue is resolved (code change merged)
- The risk is formally accepted with documented rationale
- The concern is superseded by a different approach
