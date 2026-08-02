
# Class Intent Contract: HistoricalLineGraph

**Status:** Active
**Owner:** views-reporting maintainers
**Last reviewed:** 2026-06-23
**Related ADRs:** ADR-018 (frames as the data contract)

---

## 1. Purpose

> **What is this class for?**

HistoricalLineGraph produces interactive Plotly line graphs that overlay historical observations and forecast predictions for VIEWS conflict-forecasting predictions. It is **frame-native** (epic #137, #138): it takes a `views_frames.TargetFrame` (observed history) and/or a `views_frames.PredictionFrame` (forecast samples) plus a `SpatialLevel` (CM/PGM only). It supports Highest Density Interval (HDI) band overlays and Maximum A Posteriori (MAP) traces for sample forecasts (`forecast_frame.is_sample`), with an entity dropdown for switching between countries or grid cells.

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** compute HDI or MAP statistics itself; it delegates to the frame-native `views_reporting.statistics.calculate_hdi_frame` and `calculate_map_frame`.
- This class does **not** produce static (Matplotlib) plots; `interactive=False` raises `NotImplementedError`.
- This class does **not** perform data transformation, filtering, or reconciliation.
- This class does **not** persist outputs to disk; callers save returned figures or HTML strings.
- This class does **not** support geographic (map-based) visualizations.

---

## 3. Responsibilities and Guarantees

- **Flexible frame acceptance.** Accepts `historical_frame` (`TargetFrame`) and/or `forecast_frame` (`PredictionFrame`), both optional, plus `level` (`SpatialLevel`). Raises `ValueError` if both frames are `None`.
- **Target is required.** Frames are single-target, so `targets` must be supplied to `plot_predictions_vs_historical` (it raises `RuntimeError` otherwise). The bare target name is used for history; `pred_{target}` for the forecast.
- **Entity validation.** `_validate_entity_ids()` normalizes entity IDs to a list and validates presence in available datasets. Raises `ValueError` if no valid entities are found.
- **Cutoff line (mode-aware).** When both datasets are present, draws a vertical dotted line and labels it from a **data-driven** check of where predictions fall relative to observed history; the accepted `run_type` argument feeds only the partition caption, not the mode determination:
  - **True forecast** (`max(predicted) > max(observed)`): line at the last observed month, labelled **"Forecast Start"**; predictions extend to its right.
  - **Hindcast** (`max(predicted) <= max(observed)`, e.g. a calibration rolling-origin evaluation): line at the **first predicted month** (the forecast launch), labelled **"Forecast launched (hindcast)"**, plus a caption explaining that the predictions overlay the observed values they are scored against — so a hindcast does not read as "a forecast in the past."
- **HDI bands (multiple, legend-selectable).** When `the forecast frame `is_sample` (`sample_count > 1`)`, renders an HDI band for each credible level in `hdi_levels` (default the single `alpha`) via `_create_hdi_traces()`. Each band is one legend entry named `"<pct>% HDI"` (the three lower/upper/fill traces share a `legendgroup`); the `default_hdi_level` band is shown and the others start `"legendonly"` so the reader switches/compares levels by clicking the legend. The credible level is therefore **visible** in the report.
- **Configuration injection (ADR-016).** `hdi_levels` and the default `alpha` are **parameters**, supplied by the Compose layer from `get_config()`; the Render layer never reads config directly.
- **MAP trace.** When HDI is active and MAP computation succeeds, adds a dashed MAP line (level-independent).
- **Entity dropdown.** When multiple entities are provided, creates a Plotly dropdown that toggles entity visibility via **tag-based three-state visibility** (`_create_dropdown_buttons()` over `trace_tags`): the selected entity's level-independent + default-level traces are shown, its other levels collapse to `"legendonly"`, and other entities are hidden. Robust to entities having different trace counts (see Deviation #5).
- **Entity name resolution.** Maps entity IDs to human-readable names via `views_reporting.metadata.get_name_for_index` (`_get_entity_name_map`); an accessor exception falls back to `"Entity {id}"`, and NaN labels (unknown entities) also fall back — never the literal string "nan" (C-207-era fix).

---

## 4. Inputs and Assumptions

- **Constructor requires** at least one non-None frame (`TargetFrame` historical and/or `PredictionFrame` forecast) plus a `SpatialLevel` (CM/PGM only — CY/PGY dropped). Both frames `None` raises `ValueError`.
- **Frames provide** `index.time` / `index.unit` (per-row identifiers), `index.level`, `values`, `is_sample`/`sample_count`, and `select(mask)` for per-entity subsetting.
- **Target naming convention:** Historical targets use bare names (e.g., `ged_sb`); forecast targets use `pred_` prefix (e.g., `pred_ged_sb`). The class hard-codes this convention throughout.
- **HDI/MAP computation** requires `the forecast frame `is_sample` (`sample_count > 1`)` (i.e., probabilistic forecasts with multiple posterior samples).
- **Multiple HDI levels** are supported: `hdi_levels` (each a credible mass in `(0, 1)`) are rendered as separate bands; `alpha` is the default-visible level and must be one of them. HDI for each level is computed independently from the same in-memory samples (`_get_hdi_data`); if a level fails it is skipped, and if *all* fail the entity falls back to the **MAP summary line** tagged "(HDI unavailable, MAP)" — or, when no MAP frame is available, **no fabricated line** (visible absence + a loud log) (C-11, C-207 / ADR-020: the pre-guard fallback rendered posterior draw #0, an arbitrary simulation, as the forecast). The raw sample frame never crosses into a pandas line: `_pred_df` raises on S > 1; the HDI path gates on entity presence and renders tower summaries only.
- **Entity IDs** must be present in at least one dataset's `_entity_values` to be considered valid.
- **`views_reporting.statistics.calculate_hdi`** and **`calculate_map`** must be importable and functional.

---

## 5. Outputs and Side Effects

- **`plot_predictions_vs_historical(as_html=False)`** calls `fig.show()` on each per-target figure and returns `None`.
- **`plot_predictions_vs_historical(as_html=True)`** returns a concatenated HTML string of all per-target figures, each rendered via `fig.to_html(full_html=False)`.
- **Side effects:** Logging via the module-level `logger` for warnings about missing datasets, targets, and entities. No file I/O. No state mutation on the input datasets.

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| Both frames are `None` | `ValueError` raised | `__init__` |
| No valid entity IDs found | `ValueError` raised | `_validate_entity_ids` |
| `targets` not supplied | `RuntimeError` raised | `plot_predictions_vs_historical` |
| `interactive=False` | `NotImplementedError` raised | `plot_predictions_vs_historical` |
| `_pred_df` called with a sample frame (S > 1) | `ValueError` — samples never cross the pandas seam (ADR-020/C-207) | `_pred_df` |
| All HDI levels fail for an entity | MAP summary line ("(HDI unavailable, MAP)") or, with no MAP frame, visible absence + loud log — never posterior draw #0 | `_plot_interactive` / `_entity_map_series` |
| Target not found in dataset | Logged as warning, trace skipped | `_plot_interactive`, lines 188-189, 209-210 |
| MAP data not found for entity | Logged as warning, MAP trace skipped | `_plot_interactive`, lines 244-246 |
| HDI computation fails for entity (some levels) | Logged as error, level skipped | `_plot_interactive` |
| HDI fails at ALL levels | MAP summary line rendered ("(HDI unavailable, MAP)"); with no MAP frame: no line, loud log — never posterior draw #0 (C-207/ADR-020) | `_plot_interactive` |
| `_pred_df` called with a sample frame (S > 1) | `ValueError` naming the remedy — samples never cross the pandas seam | `_pred_df` |
| Entity not in one of the frames | Logged as warning, entity excluded | `_validate_entity_ids` |

The former C-05 `AttributeError` class (HDI traces reading the historical dataset's `_time_id`) is structurally gone: the time/entity column names come from `level.index_names` via `_resolved_time_id`, independent of which frame is present.

---

## 7. Boundaries and Interactions

- **Depends on:**
  - `views_frames` -- `TargetFrame`, `PredictionFrame`, `SpatialLevel`
  - `views_reporting.metadata` -- `get_name_for_index()` (entity name resolution)
  - `views_reporting.statistics` -- `calculate_hdi_frame()`, `calculate_map_frame()` (statistical computation)
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
from views_reporting.loaders import frames_from_dataframe
from views_reporting.visualizations import HistoricalLineGraph

# Both historical and forecast
hlg = HistoricalLineGraph(
    historical_frame=hist_frame,
    forecast_frame=pred_frame,
)
html = hlg.plot_predictions_vs_historical(
    entity_ids=[180, 181],
    targets=["ged_sb"],
    as_html=True,
)

# Forecast only (non-probabilistic, no HDI)
hlg_forecast_only = HistoricalLineGraph(
    forecast_frame=point_pred_frame,
)
hlg_forecast_only.plot_predictions_vs_historical(entity_ids=[180])
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: Both datasets are None
hlg = HistoricalLineGraph(None, None)  # Raises ValueError

# NOTE: forecast-only with probabilistic samples is SUPPORTED (C-05 resolved) —
# the actually-wrong pattern is passing dataset objects / stale kwargs:
hlg = HistoricalLineGraph(
    historical_dataset=None,
    forecast_dataset=some_dataset,  # WRONG kwarg — it is forecast_frame=, a PredictionFrame
)
hlg.plot_predictions_vs_historical(entity_ids=[180])  # AttributeError in _create_hdi_traces

# WRONG: Requesting static plots
hlg.plot_predictions_vs_historical(interactive=False)  # Raises NotImplementedError
```

---

## 10. Test Alignment

**Value-level characterization (migration proof):** `tests/test_historical_characterization.py` drives the frame path (`TargetFrame` + `PredictionFrame`) and pins the exact trace y-values (historical line, HDI bounds, MAP line), trace count, and dropdown labels — unchanged numeric literals via the frame path prove behaviour preservation (epic #137, #138).

**Existing pytest tests:** `tests/test_historical_line_graph.py` covering:
- **Red:** Both-None ValueError, NotImplementedError for static, invalid entity IDs, forecast-only mode; dropdown visibility stays aligned when entities have variable trace counts (`TestDropdownVisibilityVariableCounts`, Deviation #5 regression)
- **Green:** `_generate_entity_color` format and cycling, `_get_entity_label` with/without name map; HDI credible level visible in legend (`TestHdiLevelLabel`, #88); tag-based dropdown visibility partitions traces (`TestDropdownVisibilityUniform`, #89); multiple legend-selectable HDI levels — one legend entry per level, default shown / others `legendonly`, per-level `legendgroup`, multi-entity three-state dropdown (`TestHdiLevelSelector`, #90)
- **Integration:** Forecast-only with a point (S == 1) frame, forecast-only with HDI bands (C-05 regression)

---

## 11. Evolution Notes

### Known Deviations

1. ~~C-05 Bug: `_create_hdi_traces` crashes when `historical_dataset` is `None`~~ — **RESOLVED.** Added `_resolved_time_id` property that falls back to `forecast_dataset._time_id`. All 6 unguarded accesses replaced.

2. ~~`_get_plot_data()` is dead code with latent crash~~ — **RESOLVED.** Method deleted in C-05 fix.

3. **Static plots are unimplemented.** `interactive=False` raises `NotImplementedError`. This is a permanent limitation in the current design, not a TODO.

4. **Entity validation strictness.** `_validate_entity_ids()` marks an entity as invalid if it is missing from *either* frame. This means an entity present only in the forecast frame but not in the historical frame is excluded entirely, even though the class supports forecast-only rendering per entity in `_plot_interactive()`.

5. ~~Visibility toggling math assumes fixed traces-per-entity.~~ — **RESOLVED (#89).** `_plot_interactive()` now records a per-trace `trace_owner` tag (the entity each trace belongs to), and `_create_dropdown_buttons()` builds each button's visibility by matching that tag (`visible = [owner == entity_id for owner in trace_owner]`) instead of `idx * traces_per_entity` arithmetic. The dropdown stays aligned even when entities contribute different trace counts (e.g. HDI fails for one entity and it falls back to a single forecast trace). Regression test: `TestDropdownVisibilityVariableCounts`.

6. **`_format_interactive_plot()` adds a range slider.** The x-axis `rangeslider` is always enabled, which can make the plot area feel cramped for small datasets.

7. ~~Cutoff line always labelled "Forecast Start", even for hindcasts~~ — **RESOLVED (C-37).** In a calibration/evaluation report the predictions are a held-out rolling-origin hindcast that legitimately overlays observed history; the old fixed "Forecast Start" label (pinned at the last observed month) made this read as a forecast in the past. The cutoff is now mode-aware (data-driven): hindcasts mark the launch month with a "Forecast launched (hindcast)" label + caption; true forecasts keep "Forecast Start". The caption is carried in the figure title slot.

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
