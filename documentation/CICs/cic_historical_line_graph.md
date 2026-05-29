
# Class Intent Contract: HistoricalLineGraph

**Status:** Draft  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-05-29  
**Related ADRs:** none  

---

## 1. Purpose

> **What is this class for?**

HistoricalLineGraph produces interactive Plotly line graphs that overlay historical observations and forecast predictions for VIEWS conflict-forecasting datasets. It supports Highest Density Interval (HDI) band overlays and Maximum A Posteriori (MAP) traces for probabilistic forecasts, with an entity dropdown for switching between countries or grid cells.

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** compute HDI or MAP statistics itself; it delegates to `views_reporting.statistics.calculate_hdi` and `views_reporting.statistics.calculate_map`.
- This class does **not** produce static (Matplotlib) plots; `interactive=False` raises `NotImplementedError` (line 127).
- This class does **not** perform data transformation, filtering, or reconciliation.
- This class does **not** persist outputs to disk; callers save returned figures or HTML strings.
- This class does **not** support geographic (map-based) visualizations.

---

## 3. Responsibilities and Guarantees

- **Flexible dataset acceptance.** Accepts `historical_dataset` and/or `forecast_dataset`, both optional, but raises `ValueError` if both are `None` (line 43).
- **Target resolution.** When `targets` is not provided, infers targets from the historical dataset (or strips `pred_` prefix from forecast targets if historical is absent) (lines 57-66).
- **Entity validation.** `_validate_entity_ids()` (line 280) normalizes entity IDs to a list and validates presence in available datasets. Raises `ValueError` if no valid entities are found.
- **Cutoff line.** When both datasets are present, draws a vertical dotted line at the last historical time step (line 88).
- **HDI bands.** When `forecast_dataset.sample_size > 1`, computes and renders HDI lower/upper bounds as filled bands via `_create_hdi_traces()` (line 410).
- **MAP trace.** When HDI is active and MAP computation succeeds, adds a dashed MAP line (lines 229-246).
- **Entity dropdown.** When multiple entities are provided, creates a Plotly dropdown menu for toggling entity visibility (lines 264-276).
- **Entity name resolution.** Maps entity IDs to human-readable names using `views_reporting.metadata.get_name()` for both country and priogrid datasets (lines 307-343).

---

## 4. Inputs and Assumptions

- **Constructor requires** at least one non-None dataset from `{CMDataset, PGMDataset, CYDataset, PGYDataset}`. Both `None` raises `ValueError`.
- **Datasets must have** the following attributes: `._time_id`, `._entity_id`, `._time_values`, `._entity_values`, `.targets`, `.sample_size`, `.get_subset_dataframe()`.
- **Target naming convention:** Historical targets use bare names (e.g., `ged_sb`); forecast targets use `pred_` prefix (e.g., `pred_ged_sb`). The class hard-codes this convention throughout.
- **HDI/MAP computation** requires `forecast_dataset.sample_size > 1` (i.e., probabilistic forecasts with multiple posterior samples).
- **Entity IDs** must be present in at least one dataset's `_entity_values` to be considered valid.
- **`views_reporting.statistics.calculate_hdi`** and **`calculate_map`** must be importable and functional.

---

## 5. Outputs and Side Effects

- **`plot_predictions_vs_historical(as_html=False)`** calls `fig.show()` on each per-target figure (line 141) and returns `None`.
- **`plot_predictions_vs_historical(as_html=True)`** returns a concatenated HTML string of all per-target figures (line 143), each rendered via `fig.to_html(full_html=False)` (line 278).
- **Side effects:** Logging via the module-level `logger` for warnings about missing datasets, targets, and entities. No file I/O. No state mutation on the input datasets.

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| Both datasets are `None` | `ValueError` raised | `__init__`, line 43 |
| No valid entity IDs found | `ValueError` raised | `_validate_entity_ids`, line 304 |
| No datasets available for target resolution | `RuntimeError` raised | `plot_predictions_vs_historical`, line 66 |
| `interactive=False` | `NotImplementedError` raised | `plot_predictions_vs_historical`, line 127 |
| No time_id available for formatting | `RuntimeError` raised | `_format_interactive_plot`, line 496 |
| Target not found in dataset | Logged as warning, trace skipped | `_plot_interactive`, lines 188-189, 209-210 |
| MAP data not found for entity | Logged as warning, MAP trace skipped | `_plot_interactive`, lines 244-246 |
| HDI computation fails for entity | Logged as error, falls back to simple forecast trace | `_plot_interactive`, lines 247-256 |
| Entity not in one of the datasets | Logged as warning, entity excluded | `_validate_entity_ids`, lines 293-299 |
| **`historical_dataset=None` with HDI traces** | **`AttributeError` crash** | `_create_hdi_traces`, line 415 |

The last item is a known bug (C-05): `_create_hdi_traces()` unconditionally accesses `self.historical_dataset._time_id` on line 415 to set the x-axis for HDI band traces. When `historical_dataset` is `None`, this crashes with `AttributeError`. The method should use `self.forecast_dataset._time_id` instead.

---

## 7. Boundaries and Interactions

- **Depends on:**
  - `views_pipeline_core.data.handlers` -- `CMDataset`, `PGMDataset`, `CYDataset`, `PGYDataset`, `_CDataset`, `_PGDataset`, `_ViewsDataset` (dataset types and their attributes)
  - `views_reporting.metadata` -- `get_name()` (entity name resolution)
  - `views_reporting.statistics` -- `calculate_hdi()`, `calculate_map()` (statistical computation)
  - `plotly.graph_objects` (rendering)
  - `numpy`, `pandas` (data manipulation)
- **Must not depend on:**
  - `views_reporting.mapping` (no geographic rendering)
  - `views_reporting.reconciliation` (no reconciliation logic)
  - `views_reporting.reports` (no report building)
- **Trusts:**
  - That `calculate_hdi()` and `calculate_map()` return DataFrames with columns named `pred_{target}_hdi_lower`, `pred_{target}_hdi_upper`, and `pred_{target}_map` respectively
  - That dataset `.get_subset_dataframe()` returns correctly indexed data

---

## 8. Examples of Correct Usage

```python
from views_pipeline_core.data.handlers import CMDataset
from views_reporting.visualizations import HistoricalLineGraph

# Both historical and forecast
hlg = HistoricalLineGraph(
    historical_dataset=CMDataset(hist_df),
    forecast_dataset=CMDataset(pred_df),
)
html = hlg.plot_predictions_vs_historical(
    entity_ids=[180, 181],
    targets=["ged_sb"],
    as_html=True,
)

# Forecast only (non-probabilistic, no HDI)
hlg_forecast_only = HistoricalLineGraph(
    forecast_dataset=CMDataset(point_pred_df),
)
hlg_forecast_only.plot_predictions_vs_historical(entity_ids=[180])
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: Both datasets are None
hlg = HistoricalLineGraph(None, None)  # Raises ValueError

# WRONG: Forecast-only with probabilistic samples triggers HDI, crashes on C-05
hlg = HistoricalLineGraph(
    historical_dataset=None,
    forecast_dataset=probabilistic_dataset,  # sample_size > 1
)
hlg.plot_predictions_vs_historical(entity_ids=[180])  # AttributeError in _create_hdi_traces

# WRONG: Requesting static plots
hlg.plot_predictions_vs_historical(interactive=False)  # Raises NotImplementedError
```

---

## 10. Test Alignment

**Existing pytest tests:** `tests/test_historical_line_graph.py` — 11 tests covering:
- **Red:** Both-None ValueError, NotImplementedError for static, invalid entity IDs, forecast-only mode
- **Green:** `_generate_entity_color` format and cycling, `_get_entity_label` with/without name map
- **Integration:** Forecast-only with scalar CMDataset, forecast-only with HDI bands (C-05 regression)

---

## 11. Evolution Notes

### Known Deviations

1. ~~C-05 Bug: `_create_hdi_traces` crashes when `historical_dataset` is `None`~~ — **RESOLVED.** Added `_resolved_time_id` property that falls back to `forecast_dataset._time_id`. All 6 unguarded accesses replaced.

2. ~~`_get_plot_data()` is dead code with latent crash~~ — **RESOLVED.** Method deleted in C-05 fix.

3. **Static plots are unimplemented.** `interactive=False` raises `NotImplementedError` (line 127). This is a permanent limitation in the current design, not a TODO.

4. **Entity validation strictness.** `_validate_entity_ids()` (line 288) marks an entity as invalid if it is missing from *either* dataset. This means an entity present only in the forecast dataset but not in the historical dataset is excluded entirely, even though the class supports forecast-only rendering per entity in `_plot_interactive()`.

5. **Visibility toggling math assumes fixed traces-per-entity.** `_create_dropdown_buttons()` (line 444) computes visibility using a fixed `traces_per_entity` count. However, when HDI computation fails for some entities (line 247), those entities get fewer traces, causing the visibility array to be misaligned with the actual trace list. This can result in incorrect dropdown behavior.

6. **`_format_interactive_plot()` adds a range slider.** The x-axis `rangeslider` (line 512) is always enabled, which can make the plot area feel cramped for small datasets.

### Stability

- The overall architecture (historical + forecast + optional HDI/MAP overlay with entity dropdown) is stable.
- The `pred_` prefix convention for forecast targets is baked into the design.

### Expected Changes

- Static plot support may or may not be implemented; the `NotImplementedError` is explicit.

---

## End of Contract

This document defines the **intended meaning** of `HistoricalLineGraph`.

Changes to behavior that violate this intent are bugs.  
Changes to intent must update this contract.
