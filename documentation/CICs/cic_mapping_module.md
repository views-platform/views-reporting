
# Class Intent Contract: MappingModule

**Status:** Draft  
**Owner:** views-reporting maintainers  
**Last reviewed:** 2026-05-29  
**Related ADRs:** none  

---

## 1. Purpose

> **What is this class for?**

MappingModule produces geographic choropleth visualizations (interactive Plotly or static Matplotlib) for VIEWS conflict-forecasting datasets at either country level or PRIO-GRID cell level. It loads the appropriate shapefile, merges prediction data with geometries and entity metadata, and renders maps with log-scale coloring.

---

## 2. Non-Goals (Explicit Exclusions)

- This class does **not** perform any statistical computation on the data (no aggregation, no HDI, no reconciliation).
- This class does **not** persist outputs to disk; callers are responsible for saving returned figures or HTML strings.
- This class does **not** handle non-geographic visualizations (line graphs, distributions, tables).
- This class does **not** transform or filter the underlying dataset beyond subsetting by time/entity IDs.
- This class does **not** support arbitrary shapefiles; it is hardcoded to Natural Earth country boundaries and PRIO-GRID cells bundled in `views_reporting/assets/shapefiles/`.

---

## 3. Responsibilities and Guarantees

- **Shapefile dispatch.** On construction, loads the correct shapefile based on whether the dataset is `_PGDataset` or `_CDataset`. Raises `ValueError` on any other type (line 98).
- **Geometry preparation.** Converts geometries to EPSG:4326 (WGS84), simplifies with 0.01-degree tolerance, and caches a base GeoJSON (`_prepare_base_geojson`, line 104).
- **Data-geometry merge.** `get_subset_mapping_dataframe()` (line 368) retrieves a filtered subset of the dataset, enriches it with ISO codes and country names via `views_reporting.metadata.get_isoab` and `get_name`, and merges with shapefiles to produce a `GeoDataFrame`.
- **Missing geometry handling.** Rows with missing or empty geometries are dropped by default and logged (`__check_missing_geometries`, line 206).
- **Interactive maps.** `_plot_interactive_map()` (line 417) builds an animated Plotly choropleth with time slider, play/pause buttons, hover tooltips showing original (non-log) values, and color scale fixed to the 50th-95th quantile range of log-transformed data.
- **Static maps.** `_plot_static_map()` (line 706) builds a single-time-period Matplotlib choropleth with log-scale normalization (`FuncNorm` using `np.log1p`/`np.expm1`).
- **Dispatch.** `plot_map()` (line 785) validates the target column, dispatches to interactive or static rendering, and optionally returns HTML instead of a figure object.
- **Memory management.** Explicitly deletes intermediate DataFrames and calls `gc.collect()` after GeoJSON preparation (line 139) and interactive map rendering (line 702).

---

## 4. Inputs and Assumptions

- **Constructor requires** a single `views_dataset` argument that is an instance of `_PGDataset` or `_CDataset` (from `views_pipeline_core.data.handlers`). Any other type raises `ValueError`.
- **Shapefiles must exist** at:
  - `views_reporting/assets/shapefiles/country/ne_110m_admin_0_countries.shp` (for `_CDataset`)
  - `views_reporting/assets/shapefiles/priogrid/priogrid_cell.shp` (for `_PGDataset`)
  - Missing shapefiles cause `FileNotFoundError` from `gpd.read_file()`.
- **Dataset `.dataframe`** is assumed to have a pandas-compatible MultiIndex with `_entity_id` and `_time_id` levels.
- **Dataset `.targets`** must be a list of column names present in the dataframe.
- **`views_reporting.metadata` functions** (`get_isoab`, `get_name`) must be importable and return DataFrames keyed by `_time_id` and `_entity_id`.
- **`plot_map()`** requires `target` to be in `dataset.targets` or `dataset.features`; raises `ValueError` otherwise (line 843).
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
| Dataset is not `_PGDataset` or `_CDataset` | `ValueError` raised | `__init__`, line 98 |
| Shapefile missing on disk | `FileNotFoundError` from `gpd.read_file` | `__get_country_shapefile` (line 170), `__get_priogrid_shapefile` (line 204) |
| Target not in `dataset.targets` or `dataset.features` | `ValueError` raised | `plot_map`, line 844 |
| Static plot with multiple time periods | `ValueError` raised | `plot_map`, line 870 |
| Target column missing or all-null (static only) | `ValueError` raised | `_plot_static_map`, lines 743-746 |
| Missing geometries after merge | Logged as warning, rows dropped silently | `__check_missing_geometries`, line 238 |

The missing-geometry case is a silent data-loss scenario: rows are dropped and only logged at WARNING level. Callers receive a smaller GeoDataFrame with no programmatic signal that rows were removed.

---

## 7. Boundaries and Interactions

- **Depends on:**
  - `views_pipeline_core.data.handlers` -- `_CDataset`, `_PGDataset` (dataset types and their `.dataframe`, `.targets`, `.features`, `._entity_id`, `._time_id` attributes)
  - `views_reporting.metadata` -- `get_isoab()`, `get_name()` (entity metadata enrichment)
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

**No tests exist for MappingModule.** The existing test files (`tests/test_c01_thread_safety.py`, `tests/test_c01_layer1_specification.py`) cover `PosteriorDistributionAnalyzer`, not this class.

Tests that should exist:
- **Green:** Verify that `_prepare_base_geojson()` produces valid GeoJSON with correct CRS and simplified geometries.
- **Green:** Verify that `get_subset_mapping_dataframe()` returns a GeoDataFrame with expected columns and no null geometries for known-good inputs.
- **Beige:** Verify `plot_map()` dispatches correctly to interactive vs. static and returns the correct type.
- **Red:** Verify `ValueError` is raised for unsupported dataset types, missing targets, and multi-time static plots.

---

## 11. Evolution Notes

### Known Deviations

1. **Silent geometry dropping.** `__check_missing_geometries()` (line 206) drops rows with missing geometries and only logs a warning. There is no way for callers to detect or handle this data loss programmatically. This conflicts with a fail-loud principle.

2. **Unreachable `else` branch.** `_prepare_base_geojson()` (line 128) has an `else` branch raising `ValueError` for invalid dataset type, but the constructor already validates the type. This branch is dead code.

3. **`_mapping_dataframe` instance variable used inconsistently.** `_plot_static_map()` references `self._mapping_dataframe` (line 770) for full-range colorbar normalization, but this attribute is set to `None` in `__init__` (line 100) and never assigned elsewhere in the current code. This will raise `AttributeError` or produce incorrect results if `_mapping_dataframe` is not set externally before calling static plots.

4. **Name-mangled private methods.** Methods like `__get_country_shapefile`, `__init_mapping_dataframe`, `__add_isoab`, `__check_missing_geometries` use Python's double-underscore name mangling, making subclassing and testing more difficult than necessary.

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
