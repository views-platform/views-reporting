
# Class Intent Contract: PlotDistribution

**Status:** Active  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-06-28  
**Related ADRs:** ADR-005 (Testing Doctrine), ADR-006 (Intent Contracts), ADR-018 (render from given data)  

---

## 1. Purpose

> **What is this class for?**

PlotDistribution visualizes a posterior distribution from a views-frames `PredictionFrame`, overlaying Maximum A Posteriori (MAP) estimates and Highest Density Intervals (HDI) on histogram plots. It provides two plotting methods: one combining MAP+HDI on a single plot, and one showing multiple HDI levels. It delegates all statistical computation to module-level helper functions in `dataset_statistics.py`.

**Frame-native (C-114 / #113):** the class takes a single target's `views_frames.PredictionFrame` — not a pipeline-core dataset. `frame.values` is `(n_rows, n_samples)` on a `(time, entity)` row index; `entity_id`/`time_id` select a subset of rows by boolean mask on `frame.index`, and the selected rows' samples are pooled into the plotted distribution. The `compute_single_map()` / `calculate_single_hdi()` helpers route the MAP/HDI math through the conformance-tested, deterministic `views_frames_summarize` package (on a 1-row ephemeral `PredictionFrame`). MAP on near-uniform posteriors is implementation-defined (register C-35).

Source: `views_reporting/visualizations/distributions.py`.

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** compute MAP or HDI statistics itself. It delegates to `compute_single_map()` and `calculate_single_hdi()` from `views_reporting.statistics`.
- This class does **not** manage data loading, transformation, or persistence. It receives a `PredictionFrame` and reads from it.
- This class does **not** produce non-matplotlib outputs (no HTML, no Plotly, no static image export -- only matplotlib axes).
- This class does **not** handle time-series or multi-panel layouts. Each method produces a single axes plot.
- This class does **not** support point (non-sample) frames for HDI plotting. `plot_highest_density_intervals()` requires `frame.is_sample` to be `True`.
- This class does **not** select among targets. One `PredictionFrame` holds one target; `var_name` is a display label only.

---

## 3. Responsibilities and Guarantees

- **`plot_maximum_a_posteriori()`**:
  - Plots a histogram of the pooled posterior samples, optionally filtered by entity and/or time step.
  - Overlays a single HDI region (shaded) and a MAP estimate (dashed vertical line).
  - Supports adaptive histogram binning based on data range and sample count.
  - Optionally plots a KDE overlay via seaborn's `kde=True` parameter.
  - Returns the matplotlib `Axes` object for further customization.
  - Handles empty data gracefully by displaying "No valid samples" text.

- **`plot_highest_density_intervals()`**:
  - Plots a histogram with multiple HDI regions at different credibility levels.
  - Each HDI level gets a distinct color from a seaborn colorblind palette.
  - Alphas are sorted in descending order so wider intervals are plotted first.
  - Requires a sample frame (`frame.is_sample`).
  - Returns the matplotlib `Axes` object.

- **Data slicing:** Both methods support optional `entity_id` and `time_id` filtering via `_pooled_samples()`, which masks `frame.index.unit` / `frame.index.time` by value and pools the matching rows' samples (NaNs dropped). When both are `None`, all rows are pooled.

---

## 4. Inputs and Assumptions

- **Constructor:** Accepts a `views_frames.PredictionFrame` (one target's samples). The frame provides:
  - `.values`: `(n_rows, n_samples)` float array.
  - `.index.unit` / `.index.time`: per-row entity / time id arrays (for boolean-mask selection).
  - `.index.level`: the `SpatialLevel` (CM/PGM).
  - `.is_sample`: `True` when `n_samples > 1` (required by `plot_highest_density_intervals()`).
- **`var_name`:** Optional display label used in the plot title only. **Not validated** (the frame already fixes the target).
- **`hdi_alpha` / `alphas`:** Float(s) in (0, 1). `plot_highest_density_intervals()` validates this constraint. `plot_maximum_a_posteriori()` passes `hdi_alpha` through to `calculate_single_hdi()` without explicit validation.
- **`colors`:** Optional list of color strings. For `plot_highest_density_intervals()`, if provided, length must match `len(alphas)`.

---

## 5. Outputs and Side Effects

**Outputs:**
- Both methods return a `matplotlib.axes.Axes` object. The caller can further customize the plot or embed it in a figure layout.

**Side effects:**
- Both methods may call `plt.gca()` if no axes is provided, which creates a new figure/axes as a matplotlib global side effect.
- NaN values are filtered from the pooled samples before plotting.
- No logging is performed by this class.

---

## 6. Failure Modes and Loudness

- **Non-sample frame for HDI plot:** `plot_highest_density_intervals()` raises `ValueError` if `frame.is_sample` is `False`.
- **Invalid alpha values:** `plot_highest_density_intervals()` raises `ValueError` if any alpha is not in (0, 1). `plot_maximum_a_posteriori()` does not validate `hdi_alpha` directly.
- **Color count mismatch:** `plot_highest_density_intervals()` raises `ValueError` if `len(colors) != len(alphas)`.
- **Empty data:** `plot_maximum_a_posteriori()` handles this gracefully by displaying "No valid samples" text and returning the axes. `plot_highest_density_intervals()` does not have this guard and will pass an empty array to `calculate_single_hdi()` (whose all-NaN/empty result is `(nan, nan)`).
- **Division by zero in bin width:** If all valid samples are equal, `data_range` is 0 and `bin_width` is 0, causing division by zero in adaptive binning. This edge case is unhandled.

---

## 7. Boundaries and Interactions

- **Depends on:** `matplotlib.pyplot`, `numpy`, `seaborn`, `views_frames` (the `PredictionFrame` contract). It imports **no** pipeline-core internals (C-114 / #113).
- **Public API import:** Imports `calculate_single_hdi` and `compute_single_map` from `views_reporting.statistics` (public re-exports, per D-06 resolution).
- **Indirect dependency:** Through the statistics helpers, this class indirectly depends on the `views_frames_summarize` tower estimators for all statistical computation.
- **No reverse dependencies:** No other views-reporting module imports from this class. pipeline-core re-exports the name via a back-compat shim (`modules/visualizations`).

---

## 8. Examples of Correct Usage

**Plot MAP with HDI for a specific entity and time step:**
```python
from views_reporting.visualizations.distributions import PlotDistribution

plotter = PlotDistribution(prediction_frame)  # a single-target PredictionFrame
ax = plotter.plot_maximum_a_posteriori(
    entity_id=42,
    time_id=530,
    var_name="ged_sb",
    hdi_alpha=0.95,
)
```

**Plot multiple HDI levels:**
```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots()
plotter.plot_highest_density_intervals(
    var_name="ged_sb",
    alphas=(0.5, 0.9, 0.99),
    ax=ax,
)
plt.savefig("hdi_intervals.png")
```

---

## 9. Examples of Incorrect Usage

**Using a point (non-sample) frame for HDI plot:**
```python
# WRONG: plot_highest_density_intervals requires a sample frame (is_sample=True)
plotter = PlotDistribution(point_frame)  # S == 1
plotter.plot_highest_density_intervals(var_name="ged_sb")
# Raises ValueError: "HDI plotting only available for sample (prediction) frames"
```

**Mismatched colors and alphas:**
```python
# WRONG: one color for two alpha levels
plotter.plot_highest_density_intervals(alphas=(0.5, 0.9), colors=["red"])
# Raises ValueError: "Number of colors must match number of alpha levels"
```

---

## 10. Test Alignment

**Existing pytest tests:** `tests/test_plot_distribution.py` — red-team validation (non-sample frame, invalid alpha, color-count mismatch) and green-team rendering (MAP/HDI return axes, empty-data note, entity-slice), driven by **real** `PredictionFrame`s built from the conftest forecast-df helpers.

**Invariants covered:**
- Both methods return a valid `matplotlib.axes.Axes` object.
- `plot_highest_density_intervals()` rejects non-sample frames, invalid alphas, and color-count mismatches.
- Empty data produces "No valid samples" text (for `plot_maximum_a_posteriori()`).

---

## 11. Evolution Notes

**Stable:**
- The two-method API (`plot_maximum_a_posteriori`, `plot_highest_density_intervals`).
- Delegation to the `views_frames_summarize` tower via the statistics helpers.
- Return of matplotlib `Axes` objects for composability.

**Expected to change:**
- The inconsistent empty-data handling (guarded in `plot_maximum_a_posteriori`, unguarded in `plot_highest_density_intervals`) should be unified.

### Known Deviations

1. ~~Cross-module private function import~~ — **RESOLVED** per D-06 (functions promoted to public API).
2. ~~Constructor coupled to pipeline-core `_ViewsDataset`~~ — **RESOLVED** (C-114 / #113): migrated to a views-frames `PredictionFrame`.
3. **Inconsistent empty-data handling** between the two methods (see Expected to change).
4. **`plot_maximum_a_posteriori()` does not validate `hdi_alpha`** (the (0,1) check), unlike `plot_highest_density_intervals()`.
5. **Potential division-by-zero in adaptive binning** when all valid samples are identical (`data_range == 0`). Unhandled edge case.
6. **`plot_highest_density_intervals()` requires a sample frame but `plot_maximum_a_posteriori()` does not** — it is unclear whether MAP plotting should also be restricted to sample frames.

---

## End of Contract

This document defines the **intended meaning** of `PlotDistribution`.

Changes to behavior that violate this intent are bugs.  
Changes to intent must update this contract.
