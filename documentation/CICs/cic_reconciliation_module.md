
# Class Intent Contract: ReconciliationModule

**Status:** Draft  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-05-29  
**Related ADRs:** none  

---

## 1. Purpose

> **What is this class for?**

ReconciliationModule orchestrates hierarchical forecast reconciliation between country-level and PRIO-GRID-level predictions. It validates dataset compatibility, distributes reconciliation tasks across a `ProcessPoolExecutor` for parallel processing, and updates the grid-level dataset's `reconciled_dataframe` so that grid-cell predictions sum to country-level totals while preserving spatial patterns.

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** implement the reconciliation algorithm itself; the actual proportional-scaling math lives in `ForecastReconciler.reconcile_forecast()` (in `views_reporting.statistics.statistics`).
- This class does **not** perform model training, inference, or evaluation.
- This class does **not** handle visualization or reporting of reconciliation results.
- This class does **not** modify the country-level dataset; only the grid-level dataset's `reconciled_dataframe` is updated.
- This class does **not** support reconciliation between arbitrary hierarchy levels; it is hardcoded to the country-to-grid relationship.

---

## 3. Responsibilities and Guarantees

- **Type validation.** Constructor raises `TypeError` if `c_dataset` is not `_CDataset` or `pg_dataset` is not `_PGDataset` (lines 65-68).
- **Temporal alignment validation.** Constructor raises `ValueError` if datasets have different numbers of time steps, different time unit types (e.g., `month_id` vs `year_id`), or non-overlapping time periods (lines 75-91).
- **Target intersection.** Computes `_valid_targets` as the intersection of both datasets' `.targets`. Raises `ValueError` if the intersection is empty (lines 99-106).
- **Country-to-grid cache.** Calls `build_country_to_grids_cache(self._pg_dataset)` during construction (line 73) to populate `_pg_dataset._country_to_grids_cache`, then computes `_valid_cids` as countries present in both the cache and the country dataset (lines 94-97).
- **Parallel processing.** `reconcile()` (line 193) uses `concurrent.futures.ProcessPoolExecutor` to distribute `(country, time, feature)` triples across workers. Each worker creates its own `ForecastReconciler` instance to avoid shared-state issues.
- **Progress tracking.** Tracks per-country completion and logs progress every 10 countries (lines 276-282).
- **WandB alerts.** Sends WandB alerts at initialization (line 110), on individual task failures (lines 270-274), and on completion (lines 300-303). Alerts are controlled by the `wandb_notifications` flag (only checked in `__init__`; failure alerts are always sent).
- **Result application.** After all tasks complete, iterates over successful results and calls `reconcile_pg_dataset()` (from `views_reporting.reconciliation.dataset_export`) to update the grid dataset's `reconciled_dataframe` (lines 290-297).
- **Device detection.** Automatically detects the best available PyTorch device (CUDA > MPS > CPU) via `__detect_torch_device()` (line 116).

---

## 4. Inputs and Assumptions

- **Constructor requires:**
  - `c_dataset`: An instance of `_CDataset` with country-level predictions.
  - `pg_dataset`: An instance of `_PGDataset` with grid-level predictions.
  - `wandb_notifications` (optional, default `True`): Whether to send WandB alerts.
- **Both datasets must be in prediction mode** (implied by the use of `.targets` and `to_reconciler()` which checks `dataset.is_prediction`).
- **Both datasets must cover the same time periods** with the same time unit type.
- **Both datasets must share at least one common target variable.**
- **`build_country_to_grids_cache()`** must successfully populate `_pg_dataset._country_to_grids_cache` mapping country IDs to lists of grid cell IDs.
- **`wandb` must be importable** (hard import at line 8). The `WandBModule.send_alert()` calls assume WandB is configured or will handle unconfigured state gracefully.
- **`torch` must be importable** (hard import at line 7) for device detection and tensor operations.

---

## 5. Outputs and Side Effects

- **`reconcile()` returns** the `pg_dataset.reconciled_dataframe` (line 304), which is a copy of the original grid dataframe with reconciled prediction values substituted for the processed `(country, time, feature)` triples.
- **Side effects:**
  - **Mutates `pg_dataset.reconciled_dataframe`** in-place via `reconcile_pg_dataset()` (lines 291-297). This is the primary output mechanism.
  - **Spawns child processes** via `ProcessPoolExecutor`. Each worker process creates its own `ForecastReconciler`, `_CDataset`, and `_PGDataset` instances from serialized data.
  - **Sends WandB alerts** on initialization, failures, and completion.
  - **Logging** via module-level `logger` at INFO, WARNING, and ERROR levels.
  - **Progress bars** via `tqdm` for task completion and dataset update (lines 263, 290).

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| `c_dataset` is not `_CDataset` | `TypeError` raised | `__init__`, line 66 |
| `pg_dataset` is not `_PGDataset` | `TypeError` raised | `__init__`, line 68 |
| Different number of time steps | `ValueError` raised | `__init__`, line 76 |
| Different time unit types | `ValueError` raised | `__init__`, line 81 |
| Non-overlapping time periods | `ValueError` raised | `__init__`, line 89 |
| No common targets | `ValueError` raised | `__init__`, line 103 |
| Individual worker task failure | Logged as ERROR, WandB alert sent, task skipped | `reconcile`, lines 268-274 |
| Multiple tasks fail | Logged as WARNING after all tasks complete | `reconcile`, line 285 |

Failed tasks are logged but do not halt processing. The commented-out `raise RuntimeError(...)` on line 287 shows the intention to optionally fail hard, but the current behavior is to continue and return partial results. Callers cannot distinguish a fully reconciled result from a partially reconciled one without inspecting logs.

---

## 7. Boundaries and Interactions

- **Depends on:**
  - `views_pipeline_core.data.handlers` -- `_CDataset`, `_PGDataset` (dataset types)
  - `views_pipeline_core.modules.wandb.WandBModule` -- `.send_alert()` for monitoring
  - `views_reporting.statistics` -- `ForecastReconciler` (reconciliation algorithm)
  - `views_reporting.metadata` -- `build_country_to_grids_cache()`, `get_subset_by_country_id()` (geographic hierarchy)
  - `views_reporting.reconciliation.dataset_export` -- `to_reconciler()`, `reconcile_pg_dataset()` (data conversion and result application)
  - `torch` (device detection, tensor operations)
  - `concurrent.futures` (parallel processing)
  - `wandb` (alert levels)
  - `tqdm` (progress bars)
- **Must not depend on:**
  - `views_reporting.mapping` (no visualization)
  - `views_reporting.reports` (no report building)
  - `views_reporting.visualizations` (no plotting)
- **Trusts:**
  - That `ForecastReconciler.reconcile_forecast()` correctly implements proportional scaling
  - That `to_reconciler()` correctly extracts and transforms tensors from datasets
  - That `reconcile_pg_dataset()` correctly updates the grid dataset's reconciled dataframe

---

## 8. Examples of Correct Usage

```python
from views_pipeline_core.data.handlers import CMDataset, PGMDataset
from views_reporting.reconciliation import ReconciliationModule

c_ds = CMDataset(country_predictions_df)
pg_ds = PGMDataset(grid_predictions_df)

reconciler = ReconciliationModule(c_ds, pg_ds, wandb_notifications=True)
reconciled_df = reconciler.reconcile(max_workers=16)

# Access the reconciled predictions
print(reconciled_df.head())
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: Passing datasets with different time units
c_ds = CMDataset(monthly_df)   # _time_id = 'month_id'
pg_ds = PGYDataset(yearly_df)  # _time_id = 'year_id' -- but also wrong type
reconciler = ReconciliationModule(c_ds, pg_ds)  # TypeError for pg_ds

# WRONG: Passing non-prediction datasets
c_ds = CMDataset(actuals_df)  # is_prediction = False
pg_ds = PGMDataset(actuals_df)
reconciler = ReconciliationModule(c_ds, pg_ds)  # May pass init but to_reconciler() fails

# WRONG: Datasets with no common targets
c_ds = CMDataset(df_with_targets_A)     # targets = ['pred_ged_sb']
pg_ds = PGMDataset(df_with_targets_B)   # targets = ['pred_ged_ns']
reconciler = ReconciliationModule(c_ds, pg_ds)  # Raises ValueError
```

---

## 10. Test Alignment

**No tests exist for ReconciliationModule.** The existing test files cover `PosteriorDistributionAnalyzer`. The inline tests mentioned in the `views_reporting.statistics.statistics` module test `ForecastReconciler.reconcile_forecast()` (the algorithm), not `ReconciliationModule` (the orchestrator).

Tests that should exist:
- **Green:** Verify that `reconcile()` produces grid predictions that sum to country totals for a small synthetic dataset.
- **Green:** Verify that `_valid_targets`, `_valid_cids`, and `_valid_time_ids` are correctly computed from intersecting datasets.
- **Red:** Verify `TypeError` for wrong dataset types, `ValueError` for time misalignment, and `ValueError` for no common targets.
- **Beige:** Verify that partial failures (some worker tasks fail) still produce results for successful tasks and log appropriately.
- **Red:** Verify behavior when `wandb` is not configured (should not crash).

---

## 11. Evolution Notes

### Known Deviations

1. **C-06: Dead parameters `lr`, `max_iters`, `tol`.** The `reconcile()` method (line 193) accepts `lr`, `max_iters`, and `tol` parameters and passes them through to `ForecastReconciler.reconcile_forecast()` (line 183-188 in the worker). However, `reconcile_forecast()` (in `views_reporting/statistics/statistics.py`, lines 574-648) accepts these parameters but never uses them -- it implements simple proportional scaling, not iterative optimization. The parameters exist in the API but have no effect.

2. **WandB alert inconsistency.** The `wandb_notifications` flag is checked in `__init__` via `notifications_enabled=self._wandb_notifications` (line 113), but failure alerts in `reconcile()` (line 270) and the completion alert (line 300) do not pass this flag, meaning they are always sent regardless of the user's preference.

3. **No programmatic signal for partial failure.** When worker tasks fail, they are logged and skipped (lines 268-274). The returned `reconciled_dataframe` contains un-reconciled values for failed `(country, time, feature)` triples, but there is no way for callers to detect which cells were not reconciled. The commented-out `RuntimeError` raise (line 287) confirms this was a recognized design gap.

4. **Worker creates redundant `ForecastReconciler` per task.** `_reconcile_country_worker()` (line 175) creates a new `ForecastReconciler` for every `(country, time, feature)` triple. While this avoids shared-state issues across processes, it is wasteful since `ForecastReconciler` has no mutable state. A single instance per process would suffice.

5. **Constructor creates an unused `self._reconciler`.** Line 72 creates `self._reconciler = ForecastReconciler(device=self._device)`, but this instance is never used -- each worker creates its own. This is dead state.

6. **Data serialization overhead.** The `reconcile()` method passes `c_subset` and `pg_subset` DataFrames as part of the task arguments (lines 254-258), which are serialized via pickle for each `(time, feature)` combination within a country. The same country subset is re-serialized `len(valid_time_ids) * len(valid_targets)` times per country.

### Stability

- The parallel processing architecture (ProcessPoolExecutor with static worker method) is stable.
- The validation checks in the constructor are comprehensive and loud.
- The country-to-grid mapping cache pattern is stable.

### Expected Changes

- The dead `lr`/`max_iters`/`tol` parameters should either be removed or the algorithm should be upgraded to use them.
- WandB alert sending should consistently respect the `wandb_notifications` flag.
- A mechanism for reporting partial failures (e.g., returning a set of failed triples) should be added.
- The data serialization overhead could be reduced by restructuring the task distribution to serialize each country's data only once.

---

## End of Contract

This document defines the **intended meaning** of `ReconciliationModule`.

Changes to behavior that violate this intent are bugs.  
Changes to intent must update this contract.
