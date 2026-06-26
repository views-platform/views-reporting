
# Class Intent Contract: MappingModule

**Status:** Active
**Owner:** views-reporting maintainers
**Last reviewed:** 2026-06-23
**Related ADRs:** ADR-018 (frames as the data contract)

---

## 1. Purpose

> **What is this class for?**

MappingModule produces geographic choropleth visualizations (interactive Plotly or static Matplotlib) for VIEWS conflict-forecasting predictions at either country level (CM) or PRIO-GRID cell level (PGM). It is **frame-native** (epic #137, #138): it takes a `views_frames.PredictionFrame` + a `SpatialLevel` + a target column name, loads the appropriate shapefile, merges the prediction data with geometries and entity metadata (via the `frames_to_mapping_df` adapter — see `cic_frame_mapping_adapter.md`), and renders maps with log-scale coloring.

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** perform any statistical computation on the data (no aggregation, no HDI, no reconciliation).
- This class does **not** persist outputs to disk; callers are responsible for saving returned figures or HTML strings.
- This class does **not** handle non-geographic visualizations (line graphs, distributions, tables).
- This class does **not** transform or filter the underlying dataset beyond subsetting by time/entity IDs.
- This class does **not** support arbitrary shapefiles; it is hardcoded to Natural Earth country boundaries and PRIO-GRID cells bundled in `views_reporting/assets/shapefiles/`.

---

## 3. Responsibilities and Guarantees

- **Shapefile dispatch.** On construction, loads the correct shapefile based on whether `level` is `SpatialLevel.PGM` or `SpatialLevel.CM`. Raises `ValueError` on any other value.
- **Geometry preparation (lazy).** Converts geometries to EPSG:4326 (WGS84), simplifies with 0.01-degree tolerance, and caches a base GeoJSON (`_prepare_base_geojson`) — built **lazily on first choropleth render** (#125), so the PGM raster path never triggers the ~260K-polygon simplification.
- **Data-geometry merge.** `build_mapping_dataframe(frame)` calls the frame→pandas adapter `frames_to_mapping_df` (which enriches with ISO codes and country names via the index-keyed `get_isoab_for_index` / `get_name_for_index`), merges with the shapefile, drops missing geometries, and **assigns `self._mapping_dataframe`**. `get_subset_mapping_dataframe(time_ids, entity_ids)` filters the frame by a boolean mask on `frame.index.time`/`unit` then calls `build_mapping_dataframe`.
- **Missing geometry handling.** Rows with missing or empty geometries are dropped by default and logged (`__check_missing_geometries`, line 206).
- **Interactive maps.** `_plot_interactive_map()` builds an animated Plotly choropleth with time slider, play/pause buttons, hover tooltips showing original (non-log) values, and color scale fixed to the 50th-95th quantile range of log-transformed data.
- **Interactive PGM raster (register C-26 / #125).** `_plot_interactive_raster_map()` renders the PGM lattice as a `go.Heatmap` over (lon, lat) — selected when `plot_map(raster=True)` and `level == PGM`. It embeds **no polygon GeoJSON** (payload is O(cells) scalars, not ~260K polygons), so the full grid renders within the report's byte budget; it is **faithful by construction** (one cell → one array element — no aggregation, no omission), log-coloured with a labelled colourbar, and labelled a per-cell point summary. `raster=True` is **declared** via `ReportingConfig.pgm_raster` (default off; ADR-003); it is ignored for CM (countries are not a lattice).
- **Static maps.** `_plot_static_map()` (line 706) builds a single-time-period Matplotlib choropleth with log-scale normalization (`FuncNorm` using `np.log1p`/`np.expm1`).
- **Dispatch.** `plot_map()` (line 785) validates the target column, dispatches to interactive or static rendering, and optionally returns HTML instead of a figure object.
- **Scale guard (fail-loud, register C-26).** `plot_map()` accepts an injected `max_cells` limit; if the number of rendered map entries (`len(mapping_dataframe)` — entities × time steps, the real size/memory driver) exceeds it, it raises a `ValueError` naming the count, the limit, and the override **before** building any Plotly/Matplotlib traces — rather than risk an out-of-memory failure or a multi-GB HTML file (the C-105/C-106 PGM-scale failure class). `max_cells` is read from `ReportingConfig.max_map_cells` at the Compose boundary (forecast template) and injected downward (ADR-016); the Render layer never reads config. `None` disables the guard. The **raster path is exempt** (its payload does not scale with polygon geometry — #125). Downsampling/aggregation remains deliberately out of scope (it would change output fidelity — registered C-189/C-190); raster is the faithful large-render answer.
- **Memory management.** Explicitly deletes intermediate DataFrames and calls `gc.collect()` after GeoJSON preparation (line 139) and interactive map rendering (line 702).

---

## 4. Inputs and Assumptions

- **Constructor requires** `frame` (a `views_frames.PredictionFrame`, S == 1), `level` (`SpatialLevel.CM`/`SpatialLevel.PGM`), and `target_column` (the value column name, e.g. `pred_ged_sb_map`). An invalid `level` raises `ValueError`.
- **Shapefiles must exist** at:
  - `views_reporting/assets/shapefiles/country/ne_110m_admin_0_countries.shp` (for `_CDataset`)
  - `views_reporting/assets/shapefiles/priogrid/priogrid_cell.shp` (for `_PGDataset`)
  - Missing shapefiles cause `FileNotFoundError` from `gpd.read_file()`.
- **Dataset `.dataframe`** is assumed to have a pandas-compatible MultiIndex with `_entity_id` and `_time_id` levels.
- **Dataset `.targets`** must be a list of column names present in the dataframe.
- **`views_reporting.metadata` functions** (`get_isoab_for_index`, `get_name_for_index`) must be importable (used via the `frames_to_mapping_df` adapter) and return DataFrames keyed by the `(time, entity)` MultiIndex.
- **`plot_map()`** requires `target` to be present as a column in the supplied `mapping_dataframe` (the `target_column` the module was constructed for); raises `ValueError` otherwise.
- **`plot_map()` accepts an optional `max_cells` scale limit** (injected from `ReportingConfig.max_map_cells` at the Compose boundary, ADR-016). When set and the render size (`len(mapping_dataframe)`) exceeds it, the render fails loud before any trace construction (C-26). `None` (the default for ad-hoc callers) disables the guard.
- **Static maps** require exactly one time period in the mapping dataframe; raises `ValueError` if multiple are present (line 869).

---

## 5. Outputs and Side Effects

- **`get_subset_mapping_dataframe()`** returns a `gpd.GeoDataFrame` with geometry column, ISO codes, country names, and the original target columns.
- **`plot_map(interactive=True, as_html=False)`** returns a `plotly.graph_objs.Figure`.
- **`plot_map(interactive=True, as_html=True)`** returns an HTML string containing the full Plotly figure with embedded Plotly.js.
- **`plot_map(interactive=False, as_html=False)`** returns a `matplotlib.figure.Figure`.
- **`plot_map(interactive=False, as_html=True)`** returns an HTML `<img>` tag with base64-embedded PNG.
- **Side effects:** Logging via the module-level `logger`. Explicit `gc.collect()` calls. Matplotlib figures are created but not closed by the caller (static maps are closed only when `as_html=True`, line 875).

---

## 6. Failure Modes and Loudness

| Condition | Behavior | Location |
|---|---|---|
| `level` is not `SpatialLevel.CM`/`PGM` | `ValueError` raised | `__init__` |
| Shapefile missing on disk | `FileNotFoundError` from `gpd.read_file` | `__get_country_shapefile` (line 170), `__get_priogrid_shapefile` (line 204) |
| Target not in `dataset.targets` or `dataset.features` | `ValueError` raised | `plot_map`, line 844 |
| Render size exceeds injected `max_cells` (entities × time steps) | `ValueError` raised **before** any trace construction — an early, controlled refusal (C-26) instead of a late, uncontrolled OOM / multi-GB file | `plot_map` (scale guard) |
| Static plot with multiple time periods | `ValueError` raised | `plot_map`, line 870 |
| Target column missing or all-null (static only) | `ValueError` raised | `_plot_static_map`, lines 743-746 |
| Missing geometries after merge | Logged as warning, rows dropped silently | `__check_missing_geometries`, line 238 |

The missing-geometry case is a silent data-loss scenario: rows are dropped and only logged at WARNING level. Callers receive a smaller GeoDataFrame with no programmatic signal that rows were removed.

---

## 7. Boundaries and Interactions

- **Depends on:**
  - `views_frames` -- `PredictionFrame`, `SpatialLevel` (data + level dispatch)
  - `views_reporting.mapping._frame_adapter` -- `frames_to_mapping_df` (the sole frame→pandas seam; see `cic_frame_mapping_adapter.md`)
  - `geopandas`, `plotly`, `matplotlib`, `numpy`, `pandas` (rendering)
- **Must not depend on:**
  - `views_reporting.statistics` (no statistical computation)
  - `views_reporting.reconciliation` (no reconciliation logic)
  - `views_reporting.reports` (no report building)
- **Trusts:**
  - That `_CDataset`/`_PGDataset` dataframes are well-formed with the expected MultiIndex structure
  - That shapefiles bundled in `assets/shapefiles/` are correct and complete

---

## 8. Examples of Correct Usage

```python
from views_pipeline_core.data.handlers import PGMDataset
from views_reporting.mapping import MappingModule

dataset = PGMDataset(predictions_df)
mapper = MappingModule(dataset)

# Interactive map for multiple time steps
gdf = mapper.get_subset_mapping_dataframe(time_ids=[528, 529, 530])
html = mapper.plot_map(gdf, target='pred_ged_sb', interactive=True, as_html=True)

# Static map for a single time step
gdf_single = mapper.get_subset_mapping_dataframe(time_ids=528)
fig = mapper.plot_map(gdf_single, target='pred_ged_sb', interactive=False)
```

---

## 9. Examples of Incorrect Usage

```python
# WRONG: Passing a raw DataFrame instead of a _CDataset/_PGDataset
mapper = MappingModule(some_pandas_dataframe)  # Raises ValueError

# WRONG: Static map with multiple time periods
gdf_multi = mapper.get_subset_mapping_dataframe(time_ids=[528, 529])
mapper.plot_map(gdf_multi, target='pred_ged_sb', interactive=False)  # Raises ValueError

# WRONG: Target not present in dataset
mapper.plot_map(gdf, target='nonexistent_column', interactive=True)  # Raises ValueError
```

---

## 10. Test Alignment

- **Green/Red:** `tests/test_mapping.py` — constructor shapefile dispatch by `SpatialLevel`; invalid-level raise; the C-26 scale guard (fires strictly above threshold, disabled by `None`).
- **Green (characterization):** `tests/test_mapping_characterization.py` drives the frame→adapter→shapefile path and pins the per-(time, entity) target values, the isoab/country_name join, and the row count — the migration behaviour proof (epic #137, #138).
- **Beige:** `tests/test_e2e_fixture.py` / `tests/test_e2e_synthetic.py` — full forecast report through real/synthetic frames.

---

## 11. Evolution Notes

### Known Deviations

1. **Silent geometry dropping.** `__check_missing_geometries()` drops rows with missing geometries and only logs a warning. There is no way for callers to detect or handle this data loss programmatically. This conflicts with a fail-loud principle.

2. ~~Unreachable `else` branch in `_prepare_base_geojson()`~~ — **RESOLVED (#138).** The dataset-type `else`/`ValueError` branch was removed when the constructor moved to `SpatialLevel` dispatch (CM/PGM exhaustive).

3. ~~`_mapping_dataframe` latent `AttributeError`~~ — **RESOLVED (#138).** `build_mapping_dataframe()` now assigns `self._mapping_dataframe` (the full-range geo-merged frame `_plot_static_map` reads for colorbar normalization). It is no longer left `None`.

4. **Name-mangled private methods.** Methods like `__get_country_shapefile`, `__check_missing_geometries` use Python's double-underscore name mangling, making subclassing and testing more difficult than necessary. (`__init_mapping_dataframe`/`__add_isoab` were replaced by `build_mapping_dataframe` + the `frames_to_mapping_df` adapter in #138.)

5. **No input validation on `time_ids`/`entity_ids` in `get_subset_mapping_dataframe()`.** Invalid IDs are passed through to `dataset.get_subset_dataframe()`, which may raise opaque errors.

### Stability

- The dual-rendering architecture (Plotly interactive / Matplotlib static) is stable.
- The shapefile loading and geometry simplification pipeline is stable.
- The log-scale coloring strategy (`np.log1p`) is stable and consistent across both renderers.

### Expected Changes

- The `_mapping_dataframe` issue (item 3 above) needs to be resolved.
- CDN-based Plotly.js dependency in HTML output may need to be reconsidered for offline use.

---

## End of Contract

This document defines the **intended meaning** of `MappingModule`.

Changes to behavior that violate this intent are bugs.  
Changes to intent must update this contract.
