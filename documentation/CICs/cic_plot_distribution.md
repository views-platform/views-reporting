
# Class Intent Contract: PlotDistribution

**Status:** Active  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-05-29  
**Related ADRs:** ADR-005 (Testing Doctrine), ADR-006 (Intent Contracts)  

---

## 1. Purpose

> **What is this class for?**

PlotDistribution visualizes posterior distributions from VIEWS prediction datasets, overlaying Maximum A Posteriori (MAP) estimates and Highest Density Intervals (HDI) on histogram plots. It provides two plotting methods: one combining MAP+HDI on a single plot, and one showing multiple HDI levels. It delegates all statistical computation to module-level helper functions in `dataset_statistics.py`.

Source: `views_reporting/visualizations/distributions.py`, full file (~237 lines).

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** compute MAP or HDI statistics itself. It delegates to `_simon_compute_single_map()` and `_calculate_single_hdi()` from `views_reporting.statistics.dataset_statistics`.
- This class does **not** manage data loading, transformation, or persistence. It receives a dataset object and reads from it.
- This class does **not** produce non-matplotlib outputs (no HTML, no Plotly, no static image export -- only matplotlib axes).
- This class does **not** handle time-series or multi-panel layouts. Each method produces a single axes plot.
- This class does **not** support non-prediction datasets for HDI plotting. `plot_highest_density_intervals()` requires `self._dataset.is_prediction` to be `True` (line 160).

---

## 3. Responsibilities and Guarantees

- **`plot_maximum_a_posteriori()`** (lines 20-135):
  - Plots a histogram of posterior samples for a specific variable, optionally filtered by entity and/or time step.
  - Overlays a single HDI region (shaded) and a MAP estimate (dashed vertical line).
  - Supports adaptive histogram binning based on data range and sample count (lines 80-82).
  - Optionally plots a KDE overlay via seaborn's `kde=True` parameter (line 89).
  - Returns the matplotlib `Axes` object for further customization.
  - Handles empty data gracefully by displaying "No valid samples" text (lines 71-73).

- **`plot_highest_density_intervals()`** (lines 137-236):
  - Plots a histogram with multiple HDI regions at different credibility levels.
  - Each HDI level gets a distinct color from a seaborn colorblind palette (line 201).
  - Alphas are sorted in descending order so wider intervals are plotted first (line 207).
  - Validates that dataset is a prediction dataset (line 160-161).
  - Returns the matplotlib `Axes` object.

- **Data slicing:** Both methods support optional `entity_id` and `time_id` filtering. When specified, the dataset tensor is sliced along the entity/time dimensions (lines 59-64, 175-180). When `None`, all entities/times are aggregated.

---

## 4. Inputs and Assumptions

- **Constructor:** Accepts a `_ViewsDataset` instance from `views_pipeline_core.data.handlers`. The dataset must have:
  - `.targets`: list of variable names.
  - `.to_tensor()`: method returning a numpy-compatible tensor with shape `(time, entity, ..., variable)`.
  - `._get_entity_index(entity_id)`: method to convert entity ID to tensor index.
  - `._get_time_index(time_id)`: method to convert time ID to tensor index.
  - `.is_prediction`: boolean attribute (required by `plot_highest_density_intervals()`).
- **`var_name`:** Must be a string present in `self._dataset.targets`. Validated explicitly with `ValueError` if missing (lines 50-51, 162-163).
- **`hdi_alpha` / `alphas`:** Float(s) in (0, 1). `plot_highest_density_intervals()` validates this constraint (line 167). `plot_maximum_a_posteriori()` passes it through to `_calculate_single_hdi()` without explicit validation.
- **`colors`:** Optional list of color strings. For `plot_highest_density_intervals()`, if provided, length must match `len(alphas)` (lines 202-203).

---

## 5. Outputs and Side Effects

**Outputs:**
- Both methods return a `matplotlib.axes.Axes` object. The caller can further customize the plot or embed it in a figure layout.

**Side effects:**
- Both methods may call `plt.gca()` if no axes is provided (lines 47, 187), which creates a new figure/axes as a matplotlib global side effect.
- NaN values are filtered from the data before plotting (lines 68, 184).
- No logging is performed by this class.

---

## 6. Failure Modes and Loudness

- **Invalid variable name:** Both methods raise `ValueError` if `var_name` is `None` or not in `self._dataset.targets` (lines 50-51, 162-163).
- **Non-prediction dataset for HDI plot:** `plot_highest_density_intervals()` raises `ValueError` if `self._dataset.is_prediction` is `False` (lines 160-161).
- **Invalid alpha values:** `plot_highest_density_intervals()` raises `ValueError` if any alpha is not in (0, 1) (line 167). `plot_maximum_a_posteriori()` does not validate `hdi_alpha` directly.
- **Color count mismatch:** `plot_highest_density_intervals()` raises `ValueError` if `len(colors) != len(alphas)` (line 203).
- **Empty data:** `plot_maximum_a_posteriori()` handles this gracefully by displaying "No valid samples" text and returning the axes (lines 71-73). `plot_highest_density_intervals()` does not have this guard and will pass an empty array to `_calculate_single_hdi()`, whose behavior in this case depends on `PosteriorDistributionAnalyzer.analyze()`.
- **Division by zero in bin width:** If `valid_samples.max() == valid_samples.min()` (constant data), `data_range` is 0 and `bin_width` is 0, causing division by zero at line 82. This is an unhandled edge case.

---

## 7. Boundaries and Interactions

- **Depends on:** `matplotlib.pyplot`, `numpy`, `seaborn`, `views_pipeline_core.data.handlers` (for dataset type hint).
- **Cross-module private import:** Imports `_calculate_single_hdi` and `_simon_compute_single_map` from `views_reporting.statistics.dataset_statistics` (lines 8-11). These are private functions (underscore-prefixed) in another module, creating a fragile cross-module dependency.
- **Indirect dependency:** Through the dataset_statistics helpers, this class indirectly depends on `PosteriorDistributionAnalyzer` for all statistical computation.
- **No reverse dependencies:** No other views-reporting module imports from this class (based on code inspection).

---

## 8. Examples of Correct Usage

**Plot MAP with HDI for a specific entity and time step:**
```python
from views_reporting.visualizations.distributions import PlotDistribution

plotter = PlotDistribution(dataset=prediction_dataset)
ax = plotter.plot_maximum_a_posteriori(
    entity_id=42,
    time_id=530,
    var_name="ged_sb_dep",
    hdi_alpha=0.95,
)
```

**Plot multiple HDI levels:**
```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
plotter.plot_highest_density_intervals(
    var_name="ged_sb_dep",
    alphas=(0.5, 0.9, 0.99),
    ax=ax,
)
plt.savefig("hdi_intervals.png")
```

---

## 9. Examples of Incorrect Usage

**Using with a non-prediction dataset for HDI plot:**
```python
# WRONG: plot_highest_density_intervals requires is_prediction=True
plotter = PlotDistribution(dataset=actuals_dataset)
plotter.plot_highest_density_intervals(var_name="ged_sb_dep")
# Raises ValueError: "HDI plotting only available for prediction dataframes"
```

**Omitting var_name:**
```python
# WRONG: var_name is required, not optional despite Optional type hint
plotter.plot_maximum_a_posteriori()
# Raises ValueError: "Invalid variable None. Choose from [...]"
```

---

## 10. Test Alignment

**Existing pytest tests:** None. No files in `tests/` cover `PlotDistribution`.

**Invariants that should be tested (but are not):**
- Both methods return a valid `matplotlib.axes.Axes` object.
- HDI shading region is correctly positioned between `hdi_min` and `hdi_max`.
- MAP vertical line is positioned at the computed MAP value.
- `plot_highest_density_intervals()` rejects non-prediction datasets.
- Empty data produces "No valid samples" text (for `plot_maximum_a_posteriori()`).
- Color count mismatch raises `ValueError`.
- Variable name validation raises `ValueError` for unknown variables.

---

## 11. Evolution Notes

**Stable:**
- The two-method API (`plot_maximum_a_posteriori`, `plot_highest_density_intervals`).
- Delegation to `PosteriorDistributionAnalyzer` via dataset_statistics helpers.
- Return of matplotlib `Axes` objects for composability.

**Expected to change:**
- The cross-module private import should be refactored. Either the helpers should be made public, or PlotDistribution should use `PosteriorDistributionAnalyzer` directly.
- Tests need to be written.
- The inconsistent empty-data handling (guarded in `plot_maximum_a_posteriori`, unguarded in `plot_highest_density_intervals`) should be unified.

### Known Deviations

1. **Cross-module private function import** (lines 8-11). `PlotDistribution` imports `_calculate_single_hdi` and `_simon_compute_single_map` from `views_reporting.statistics.dataset_statistics`. These are underscore-prefixed functions, conventionally signaling "internal to this module." Importing them from another module breaks this convention and creates a fragile coupling -- any rename or refactor of these private helpers will break this visualization class.

2. **Inconsistent empty-data handling.** `plot_maximum_a_posteriori()` gracefully handles empty data by displaying "No valid samples" (lines 71-73). `plot_highest_density_intervals()` has no such guard and will pass empty data downstream, potentially causing errors in `_calculate_single_hdi()`.

3. **`plot_maximum_a_posteriori()` does not validate `hdi_alpha`** (the range (0,1) check). It is passed directly to `_calculate_single_hdi()`. `plot_highest_density_intervals()` validates `alphas` explicitly (line 167). This inconsistency means invalid alpha values produce different error experiences depending on which method is called.

4. **Potential division-by-zero in adaptive binning** (line 82). When all valid samples are identical, `data_range` is 0, causing `bin_width = 0 / ...` and then `int(data_range / bin_width)` which is `0/0`. This edge case is unhandled.

5. **No pytest tests exist.** The class has zero automated test coverage.

6. **`plot_highest_density_intervals()` checks `is_prediction` but `plot_maximum_a_posteriori()` does not** (line 160 vs. absent). It is unclear whether MAP plotting should also be restricted to prediction datasets.

---

## End of Contract

This document defines the **intended meaning** of `PlotDistribution`.

Changes to behavior that violate this intent are bugs.  
Changes to intent must update this contract.
